# Online schema change bằng bảng phụ, trigger hoặc binary log

Thay đổi schema trên một bảng MySQL lớn có thể mất nhiều thời gian và ảnh hưởng trực tiếp tới ứng dụng. Một lệnh `ALTER TABLE` có thể phải tạo lại bảng, đọc và ghi hàng triệu bản ghi, xây dựng index, tạo tải I/O lớn hoặc giữ metadata lock ở thời điểm bắt đầu và kết thúc. Nếu triển khai không đúng, thay đổi schema có thể làm tăng độ trễ, gây replica lag hoặc khiến ứng dụng không ghi được trong lúc cutover.

**Online schema change** là nhóm kỹ thuật giúp thay đổi cấu trúc bảng trong khi hệ thống vẫn tiếp tục phục vụ phần lớn truy vấn. Các cách phổ biến gồm dùng online DDL tích hợp của MySQL, tạo bảng phụ rồi đồng bộ thay đổi bằng trigger, hoặc tạo bảng phụ rồi phát lại thay đổi từ binary log. Công cụ như `pt-online-schema-change` và `gh-ost` triển khai hai hướng sau.

Không có phương pháp nào bảo đảm hoàn toàn không khóa. Cả online DDL lẫn công cụ tạo bảng phụ đều có thể cần metadata lock ngắn ở các thời điểm quan trọng. Thiết kế đúng cần chọn phương pháp theo loại thay đổi, kích thước bảng, khóa chính, foreign key, topology replication, khả năng quan sát và giới hạn downtime.

Bài học sử dụng MySQL 8.0 và các thuật ngữ `SOURCE`/`REPLICA`. Tính năng DDL trực tuyến, yêu cầu công cụ và tùy chọn cụ thể phụ thuộc phiên bản; luôn thử trên đúng phiên bản và cấu trúc bảng trước khi chạy production.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt online DDL tích hợp với online schema change dựa trên bảng phụ.
- Mô tả cách trigger và binary log đồng bộ thay đổi trong khi dữ liệu được copy.
- Chọn giữa native DDL, `pt-online-schema-change` và `gh-ost` theo đặc điểm bảng.
- Nhận diện yêu cầu về primary key, trigger, foreign key, binary log và replication.
- Lập kế hoạch copy theo chunk, throttling, cutover và xử lý metadata lock.
- Triển khai schema change theo hướng expand-contract để ứng dụng tương thích trong suốt quá trình.
- Kiểm tra dữ liệu, replica và khả năng phục hồi sau thay đổi.

## 1. Vì sao cần online schema change?

Giả sử bảng `orders` có hàng trăm triệu dòng và cần thêm một cột, đổi kiểu dữ liệu hoặc xây dựng index. Một lệnh DDL có thể thực hiện một trong các công việc sau:

- Thay đổi metadata mà không phải xây dựng lại toàn bộ bảng.
- Sửa cấu trúc trong khi vẫn cho phép một số thao tác đọc/ghi đồng thời.
- Tạo bản sao bảng, copy dữ liệu sang cấu trúc mới rồi đổi tên bảng.

Chi phí phụ thuộc loại DDL, storage engine, phiên bản MySQL, kích thước hàng, index, constraint và tải đồng thời. Một thao tác thêm cột có thể là `INSTANT` trên phiên bản hỗ trợ, trong khi đổi kiểu cột hoặc thay đổi định dạng hàng có thể yêu cầu rebuild. Không nên suy luận từ tên thao tác rằng nó luôn nhanh hoặc luôn không khóa.

Online schema change thường được cân nhắc khi:

- Bảng lớn và không thể chấp nhận thời gian copy/rebuild trong một cửa sổ bảo trì dài.
- Ứng dụng cần tiếp tục đọc/ghi trong lúc dữ liệu được chuyển sang cấu trúc mới.
- Native DDL không cung cấp algorithm/lock phù hợp cho thay đổi cần thực hiện.
- Cần kiểm soát tốc độ copy, replica lag và thời điểm cutover.

Với bảng nhỏ hoặc DDL được MySQL hỗ trợ bằng `ALGORITHM=INSTANT`, native DDL thường đơn giản và ít thành phần vận hành hơn. Công cụ tạo bảng phụ có chi phí lưu trữ và ghi bổ sung, nên không phải lựa chọn mặc định cho mọi thay đổi.

## 2. Đánh giá native online DDL trước

MySQL InnoDB hỗ trợ các thuật toán DDL khác nhau. Ba tên thường gặp là:

| Algorithm | Cách hoạt động khái quát | Chi phí và giới hạn |
|---|---|---|
| `INSTANT` | Thay đổi metadata mà không rebuild toàn bộ bảng trong các trường hợp được hỗ trợ | Nhanh, ít I/O; chỉ áp dụng cho danh sách thao tác và điều kiện cụ thể theo phiên bản |
| `INPLACE` | InnoDB thực hiện thay đổi bằng cơ chế nội bộ; có thể rebuild hoặc không tùy DDL | Có thể vẫn đọc/ghi đồng thời nhưng tiêu tốn I/O, CPU và dung lượng đáng kể |
| `COPY` | Tạo bản sao bảng mới rồi copy dữ liệu | Thường tốn thời gian và có hạn chế đồng thời; có thể chặn ghi trong phần lớn thao tác |

`INPLACE` không có nghĩa là không rebuild. `INSTANT` cũng không có nghĩa mọi thao tác sau đó đều miễn phí: MySQL vẫn cần cập nhật metadata, kiểm tra điều kiện và có thể phải chờ metadata lock.

### 2.1. Kiểm tra algorithm và lock

Trước khi chạy DDL, kiểm tra phiên bản và khả năng của thao tác. Trên MySQL 8.0.18 trở lên, có thể dùng `EXPLAIN ALTER TABLE` để xem kế hoạch DDL được hỗ trợ:

```sql
EXPLAIN ALTER TABLE orders
  ADD COLUMN source_channel VARCHAR(30) NULL;
```

Đây là bước dự đoán, không thay thế thử nghiệm trên bản sao dữ liệu đại diện. Có thể yêu cầu rõ algorithm và mức khóa để MySQL báo lỗi nếu không đáp ứng:

```sql
ALTER TABLE orders
  ADD COLUMN source_channel VARCHAR(30) NULL,
  ALGORITHM = INSTANT;
```

Hoặc với thao tác hỗ trợ DML đồng thời:

```sql
ALTER TABLE orders
  ADD INDEX idx_orders_created_at (created_at),
  ALGORITHM = INPLACE,
  LOCK = NONE;
```

`LOCK=NONE` yêu cầu MySQL cho phép đọc và ghi đồng thời trong giai đoạn DDL theo khả năng của thao tác. Nếu thao tác không hỗ trợ, MySQL sẽ báo lỗi thay vì tự chuyển sang mức khóa chặt hơn. Tuy nhiên, các giai đoạn chuẩn bị và hoàn tất vẫn cần metadata lock.

### 2.2. Metadata lock

MySQL dùng metadata lock (MDL) để bảo vệ định nghĩa bảng khi session đang truy cập đối tượng. DDL cần lấy metadata lock độc quyền ở một số thời điểm. Một transaction dài đang giữ metadata lock chia sẻ có thể khiến `ALTER TABLE` phải chờ; khi DDL chờ, truy vấn mới cũng có thể bị xếp hàng phía sau tùy tình huống.

Trước khi thay đổi schema:

- Kiểm tra transaction dài và session đang mở bảng.
- Tránh để migration bắt đầu trong lúc có batch hoặc báo cáo chạy lâu.
- Theo dõi `performance_schema.metadata_locks` và process list.
- Đặt thời gian chờ phù hợp, ví dụ `lock_wait_timeout`, trong session migration.
- Chuẩn bị cách dừng DDL đang chờ trước khi nó tạo hàng đợi truy vấn.

Kiểm tra metadata lock:

```sql
SELECT
  OBJECT_SCHEMA,
  OBJECT_NAME,
  LOCK_TYPE,
  LOCK_DURATION,
  LOCK_STATUS,
  OWNER_THREAD_ID
FROM performance_schema.metadata_locks
WHERE OBJECT_SCHEMA = 'app'
  AND OBJECT_NAME = 'orders';
```

Kết quả cần được đối chiếu với `performance_schema.threads` hoặc `SHOW PROCESSLIST` để tìm session giữ hoặc chờ lock. Không kill session chỉ dựa trên một dòng kết quả; xác định chủ sở hữu transaction và tác động nghiệp vụ trước.

## 3. Mô hình bảng phụ (shadow table)

Các công cụ online schema change thường tạo một bảng phụ có cấu trúc mới, copy dữ liệu từ bảng gốc sang bảng phụ, đồng bộ những thay đổi phát sinh trong lúc copy, rồi đổi vai trò hai bảng ở thời điểm cutover.

Luồng tổng quát:

```text
                Bảng gốc: orders
                (ứng dụng đang dùng)
                       |
             +---------+---------+
             |                   |
        Copy theo chunk      DML mới từ ứng dụng
             |                   |
             v                   v
       Bảng phụ: orders_new <--- đồng bộ thay đổi
             |
             |  kiểm tra dữ liệu và lag
             v
       Chờ thời điểm cutover
             |
             v
       Đổi tên bảng trong một bước
             |
             v
       orders = bảng mới
       orders_old = bảng cũ (tạm giữ)
```

Trong thời gian copy, bảng gốc vẫn là nơi ứng dụng đọc/ghi. Bảng phụ dần được lấp đầy và nhận các thay đổi mới. Khi hai bảng đã đồng bộ, công cụ cần lấy metadata lock để đổi tên hoặc hoán đổi bảng. Cutover thường ngắn hơn rebuild toàn bộ bảng nhưng vẫn có thể bị chặn bởi transaction dài.

Hai cách đồng bộ phổ biến:

- **Trigger-based:** trigger trên bảng gốc ghi thay đổi tương ứng sang bảng phụ.
- **Binlog-based:** công cụ đọc row event từ binary log rồi áp dụng vào bảng phụ.

Không nên tự tạo shadow table và đồng bộ bằng trigger/binlog nếu chưa xử lý đầy đủ thứ tự sự kiện, khóa chính, lỗi retry, DDL đồng thời, foreign key và cutover. Công cụ chuyên dụng đã xử lý nhiều tình huống khó này, nhưng vẫn cần cấu hình và giám sát đúng.

## 4. Đồng bộ bằng trigger: pt-online-schema-change

`pt-online-schema-change` (pt-osc) thuộc Percona Toolkit. Công cụ tạo bảng mới với cấu trúc đã thay đổi, thêm trigger trên bảng gốc để đồng bộ DML, copy dữ liệu theo chunk, sau đó hoán đổi bảng.

### 4.1. Cách hoạt động

Quy trình khái quát:

1. Đọc định nghĩa bảng gốc và tạo bảng phụ với thay đổi schema được yêu cầu.
2. Tạo trigger trên bảng gốc để phản ánh `INSERT`, `UPDATE` và `DELETE` sang bảng phụ.
3. Copy dữ liệu hiện có theo từng chunk dựa trên index phù hợp.
4. Theo dõi tải hệ thống và replication lag; điều chỉnh tốc độ copy hoặc tạm dừng.
5. Khi copy hoàn tất, chờ điều kiện cutover và metadata lock.
6. Đổi tên bảng gốc và bảng phụ trong một thao tác rename nhiều bảng.
7. Dọn bảng cũ và trigger theo chính sách giữ lại/rollback đã chọn.

Trigger giúp các thay đổi mới được phản ánh ngay trong bảng phụ trong khi copy dữ liệu cũ. Tuy nhiên, trigger chạy đồng bộ trong transaction của ứng dụng, nên tạo thêm công việc cho mỗi DML và có thể làm tăng latency. Nếu trigger lỗi, câu lệnh DML gốc có thể thất bại theo; đây là một phần cần tính trong đánh giá rủi ro.

### 4.2. Yêu cầu và giới hạn

- Bảng cần primary key hoặc unique index phù hợp để công cụ copy theo chunk và xác định hàng.
- Tài khoản chạy công cụ cần quyền đọc schema, tạo/xóa bảng, tạo trigger, thao tác dữ liệu và thực hiện rename theo yêu cầu của phiên bản/tool.
- Bảng có trigger sẵn cần được kiểm tra kỹ. Khả năng hỗ trợ nhiều trigger và cách pt-osc xử lý trigger hiện hữu phụ thuộc phiên bản MySQL và Percona Toolkit.
- Foreign key tham chiếu tới bảng gốc làm cutover phức tạp vì cần bảo đảm bảng con tham chiếu đúng bảng mới sau rename.
- Trigger có thể xung đột với logic ứng dụng, audit hoặc replication filter; không chạy song song nhiều migration trên cùng bảng.
- Tên bảng phụ, trigger và bảng cũ cần được theo dõi để tránh xóa nhầm dữ liệu sau một lần migration lỗi.

Nếu bảng không có primary key hoặc unique index phù hợp, không nên cố chạy pt-osc rồi hy vọng công cụ tự xử lý. Cần đánh giá khả năng thêm khóa trước, dùng native DDL hoặc chọn phương pháp khác.

### 4.3. Ví dụ chạy thử

Ví dụ dưới đây minh họa thay đổi thêm cột và chạy chế độ thử:

```bash
pt-online-schema-change \
  --alter "ADD COLUMN source_channel VARCHAR(30) NULL" \
  --dry-run \
  D=app,t=orders
```

Sau khi xác minh kế hoạch, quyền, trigger, foreign key và tải thử, mới chạy migration thật theo quy trình đã phê duyệt:

```bash
pt-online-schema-change \
  --alter "ADD COLUMN source_channel VARCHAR(30) NULL" \
  --execute \
  D=app,t=orders
```

Đây là ví dụ cú pháp, chưa phải lệnh production hoàn chỉnh. Cần cấu hình kết nối an toàn, chính sách load/replica lag, thời gian chờ cutover, cách xử lý foreign key và quy tắc giữ bảng cũ. Không truyền mật khẩu trực tiếp trong command line hoặc lưu bí mật trong shell history.

Một số tùy chọn thường được cân nhắc:

| Tùy chọn | Mục đích |
|---|---|
| `--dry-run` | Tạo và kiểm tra kế hoạch mà không thực thi migration hoàn chỉnh |
| `--execute` | Thực hiện thay đổi thật |
| `--chunk-time` | Điều chỉnh kích thước chunk theo thời gian mục tiêu |
| `--max-load` | Tạm dừng khi một số status variable vượt ngưỡng tải |
| `--critical-load` | Dừng migration khi tải vượt ngưỡng nguy hiểm |
| `--max-lag` | Điều tiết theo replica lag được công cụ theo dõi |
| `--alter-foreign-keys-method` | Chọn cách xử lý bảng con có foreign key tham chiếu tới bảng được thay đổi |

Tên và hành vi tùy chọn phụ thuộc bản Percona Toolkit. Đọc `pt-online-schema-change --help` và tài liệu đúng phiên bản; đặc biệt không chọn phương thức foreign key chỉ để làm migration chạy qua mà chưa kiểm tra thời gian khóa và tính toàn vẹn.

### 4.4. Foreign key và cutover

Khi bảng khác tham chiếu `orders`, đổi tên bảng có thể khiến quan hệ foreign key tiếp tục trỏ tới bảng cũ hoặc yêu cầu công cụ cập nhật constraint ở bảng con. Một số phương thức xử lý có thể cần rebuild bảng con hoặc tạo khoảng thời gian nhạy cảm khi swap.

Trước migration có foreign key:

- Liệt kê toàn bộ bảng con và constraint tham chiếu.
- Kiểm tra số lượng và kích thước bảng con.
- Đọc kỹ tác động của `--alter-foreign-keys-method` ở phiên bản tool đang dùng.
- Ước lượng thời gian khóa và dung lượng cần thiết khi rebuild bảng con.
- Thử cả đường thành công lẫn trường hợp cutover bị trì hoãn.

Nếu phương thức xử lý foreign key không đáp ứng giới hạn downtime, cần chọn chiến lược schema khác hoặc cửa sổ bảo trì rõ ràng. Không bỏ constraint trong production chỉ để đơn giản hóa cutover nếu chưa có biện pháp bảo vệ toàn vẹn tương đương.

## 5. Đồng bộ bằng binary log: gh-ost

`gh-ost` là công cụ online schema migration dùng binary log để nhận biết thay đổi trên bảng gốc và áp dụng chúng vào bảng phụ. Công cụ không dựa vào trigger trên bảng gốc; thay vào đó, nó đọc row event từ binlog và điều khiển việc copy/cập nhật bảng phụ.

### 5.1. Cách hoạt động

Luồng khái quát:

1. Tạo bảng ghost với schema mới.
2. Copy dữ liệu hiện có theo chunk sang bảng ghost.
3. Đọc binary log để theo dõi các thay đổi phát sinh trên bảng gốc.
4. Áp dụng row event vào bảng ghost theo đúng thứ tự cần thiết.
5. Điều tiết tốc độ dựa trên tải, replica lag hoặc tín hiệu throttling.
6. Khi dữ liệu đã đồng bộ, thực hiện cutover bằng cách đổi tên bảng trong một thao tác có kiểm soát.

Vì không thêm trigger vào bảng gốc, gh-ost tránh được chi phí thực thi trigger trên mỗi câu DML. Đổi lại, nó phụ thuộc chặt vào binary log, định dạng row event, retention và khả năng đọc/giải mã binlog của công cụ.

### 5.2. Điều kiện cần kiểm tra

- Binary logging phải bật trên server cung cấp sự kiện.
- `binlog_format=ROW` là yêu cầu quan trọng của cách làm việc dựa trên row event.
- `binlog_row_image=FULL` là cấu hình cần có cho các phiên bản gh-ost phổ biến; không giả định `MINIMAL` cung cấp đủ thông tin để công cụ áp dụng row event.
- Nếu gh-ost đọc binlog từ replica thay vì primary, replica thường cần `log_replica_updates=ON` để các sự kiện upstream xuất hiện trong binlog cục bộ.
- Binary log cần được giữ đủ lâu để công cụ không mất đoạn sự kiện trong quá trình migration.
- Bảng cần primary key hoặc unique key phù hợp để copy và xác định hàng.
- gh-ost không hỗ trợ migration bảng có foreign key; nếu bảng hoặc quan hệ tham chiếu có foreign key, chọn phương án khác hoặc xác minh giới hạn của bản công cụ cụ thể trước khi thiết kế.
- Cần đánh giá trigger hiện có, partitioning, replication topology và các tính năng bảng mà phiên bản gh-ost hỗ trợ.

Kiểm tra cấu hình binlog và danh sách file hiện có:

```sql
SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
  'log_bin',
  'binlog_format',
  'binlog_row_image',
  'log_replica_updates',
  'binlog_expire_logs_seconds'
);

SHOW BINARY LOGS;
```

Trên các phiên bản cũ, tên `log_replica_updates` có thể là `log_slave_updates`. Không mặc định gh-ost hỗ trợ mọi loại bảng; xác nhận ma trận hỗ trợ của đúng phiên bản trước khi chọn công cụ.

### 5.3. Throttling và nguồn binlog

gh-ost có thể đọc binlog từ primary hoặc từ replica được chỉ định. Đọc từ replica có thể giảm tải một số thao tác đọc trên primary, nhưng đòi hỏi replica có binlog đầy đủ và `log_replica_updates` phù hợp. Cần kiểm tra replica đó không bị lag quá lớn và công cụ đang đọc đúng nguồn.

Throttling giúp giảm tốc độ copy khi hệ thống đang bận. Có thể theo dõi replica lag, tải MySQL, thời gian query và các tín hiệu vận hành khác. Nếu binlog bị purge trước khi công cụ đọc tới, migration có thể không tiếp tục được an toàn; cần dừng và đánh giá lại trạng thái thay vì tự bỏ qua sự kiện.

Ví dụ một lệnh gh-ost ở dạng khung cấu hình:

```bash
gh-ost \
  --host=db-primary.example \
  --user=gh_ost \
  --database=app \
  --table=orders \
  --alter="ADD COLUMN source_channel VARCHAR(30) NULL" \
  --allow-on-master \
  --throttle-control-replicas="db-replica-1.example" \
  --max-load="Threads_running=40" \
  --critical-load="Threads_running=80" \
  --execute
```

Các tham số trong ví dụ chỉ minh họa ý tưởng; cách chọn host, replica, quyền, cờ cho phép chạy trên primary và ngưỡng tải phụ thuộc topology cùng phiên bản gh-ost. Hãy chạy chế độ kiểm tra phù hợp, đọc output, xác minh binlog settings và dùng file cấu hình bảo mật cho thông tin xác thực. Không sao chép nguyên ngưỡng `Threads_running` sang môi trường khác.

### 5.4. Khi binlog không đủ

Nếu binlog bị purge, đổi định dạng, thiếu row image hoặc công cụ không thể đọc sự kiện trong khoảng thời gian cần thiết, bảng ghost có thể không phản ánh đầy đủ thay đổi của bảng gốc. Khi đó không được cutover. Cần xác định điểm binlog cuối cùng đã áp dụng, kiểm tra dữ liệu và khởi động lại migration theo quy trình an toàn nếu cần.

## 6. So sánh pt-osc, gh-ost và native DDL

| Tiêu chí | Native online DDL | pt-online-schema-change | gh-ost |
|---|---|---|---|
| Cơ chế | Algorithm DDL của InnoDB | Shadow table + trigger | Shadow table + binlog event |
| Thay đổi bảng gốc | MySQL xử lý trực tiếp | Tạo trigger trên bảng gốc | Đọc binlog, không cần trigger đồng bộ trên bảng gốc |
| Tải ghi thêm | Tùy DDL và algorithm | Trigger chạy theo DML, tăng chi phí ghi | Công cụ đọc/apply binlog và ghi bảng ghost |
| Yêu cầu binlog | Không phải yêu cầu chung cho DDL | Cần xem xét replication và binlog theo topology | Là nguồn đồng bộ cốt lõi |
| Trigger hiện hữu | Không tạo trigger migration | Có thể xung đột hoặc cần hỗ trợ theo phiên bản | Không dùng trigger migration nhưng vẫn cần kiểm tra giới hạn bảng |
| Foreign key | MySQL xử lý theo DDL | Có phương thức riêng, có thể phức tạp | Không hỗ trợ bảng có foreign key trong các phiên bản phổ biến |
| Điều tiết tải | Khả năng điều khiển hạn chế hơn | Chunk/load/lag controls | Throttling và điều khiển cutover linh hoạt |
| Cutover | Hoàn tất DDL và metadata lock | Rename bảng, cần metadata lock | Rename bảng, cần metadata lock |
| Độ phức tạp vận hành | Thấp hơn nếu DDL phù hợp | Cao hơn, cần quản lý trigger và FK | Cao hơn, cần quản lý binlog và topology |

Chọn native DDL nếu thao tác được hỗ trợ với algorithm và lock chấp nhận được. Chọn pt-osc khi trigger-based copy phù hợp với bảng và topology. Cân nhắc gh-ost khi muốn tránh trigger, có binlog row-based phù hợp và bảng không vướng giới hạn của công cụ. Với foreign key hoặc cấu trúc đặc biệt, cần thử nghiệm kỹ hoặc chọn cửa sổ bảo trì.

## 7. Thiết kế ứng dụng theo expand-contract

Online schema change chỉ giải quyết phần thay đổi cấu trúc dữ liệu. Ứng dụng cũng cần tương thích với schema cũ và mới trong suốt quá trình triển khai. Mẫu **expand-contract** chia migration thành các bước tương thích ngược.

Ví dụ cần đổi `orders.customer_name` sang `customer_display_name`:

### Giai đoạn 1: Expand

Thêm cột mới, giữ cột cũ:

```sql
ALTER TABLE orders
  ADD COLUMN customer_display_name VARCHAR(200) NULL,
  ALGORITHM = INSTANT;
```

Chỉ dùng `INSTANT` nếu phiên bản và điều kiện bảng hỗ trợ. Nếu không, chọn DDL/tool khác sau khi đánh giá.

### Giai đoạn 2: Dual write hoặc tương thích đọc

Triển khai ứng dụng có thể ghi cả hai cột hoặc ghi cột mới và duy trì dữ liệu cũ trong giai đoạn chuyển tiếp. Tránh để phiên bản ứng dụng cũ không hiểu cột mới hoặc phiên bản mới giả định dữ liệu đã được backfill đầy đủ.

### Giai đoạn 3: Backfill

Điền dữ liệu cũ sang cột mới theo batch có checkpoint:

```sql
UPDATE orders
SET customer_display_name = customer_name
WHERE id > 0
  AND id <= 10000
  AND customer_display_name IS NULL;
```

Ứng dụng cần lặp theo các khoảng khóa chính tiếp theo, commit từng batch và lưu checkpoint. Ví dụ trên minh họa một batch; điều kiện và kích thước batch cần phù hợp với index, tải và dữ liệu thực tế.

### Giai đoạn 4: Switch reads

Sau khi đối chiếu số lượng và giá trị, chuyển ứng dụng đọc cột mới. Theo dõi lỗi và kết quả nghiệp vụ trong thời gian quan sát.

### Giai đoạn 5: Contract

Khi không còn phiên bản ứng dụng nào phụ thuộc cột cũ, xóa cột cũ trong một migration riêng:

```sql
ALTER TABLE orders
  DROP COLUMN customer_name;
```

Việc xóa cột có thể cần rebuild hoặc algorithm khác tùy phiên bản; phải đánh giá trước khi thực hiện. Giữ hai cột trong giai đoạn chuyển tiếp giúp rollback ứng dụng dễ hơn, nhưng cần xác định thời điểm dừng dual write và nguồn dữ liệu có thẩm quyền.

## 8. Lập kế hoạch migration production

Một migration an toàn bắt đầu bằng việc thu thập thông tin bảng và workload:

```sql
SHOW CREATE TABLE app.orders\G
SHOW TABLE STATUS FROM app LIKE 'orders'\G
SHOW INDEX FROM app.orders;
```

Kiểm tra thêm:

- Số dòng, dung lượng dữ liệu và index.
- Primary key, unique key, foreign key, partition và trigger hiện có.
- Các truy vấn đọc/ghi quan trọng, transaction dài và giờ cao điểm.
- Binary log format, row image, retention và replica topology.
- Dung lượng đĩa cho bảng phụ, binlog, relay log, temporary file và backup.
- Tài khoản, quyền và cách kết nối của công cụ migration.
- Khả năng tương thích của ứng dụng với schema trong từng giai đoạn.

### 8.1. Thử nghiệm trước

Thử trên bản sao có kích thước và workload gần production. Đo:

- Thời gian tạo bảng phụ và tốc độ copy.
- CPU, disk I/O, dung lượng tăng thêm và network throughput.
- Tác động đến latency của DML trên bảng gốc.
- Replica lag và thời gian áp dụng binlog.
- Thời gian chờ metadata lock và cutover.
- Cách công cụ phản ứng khi bị throttle, dừng, restart hoặc gặp lỗi.

Không chỉ đo thời gian chạy trung bình. Cần đo p95/p99 latency và tác động tới các truy vấn quan trọng trong lúc migration.

### 8.2. Điều tiết tải

Đặt giới hạn tải dựa trên baseline production. Có thể tạm dừng hoặc giảm tốc độ copy khi:

- `Threads_running` hoặc CPU vượt ngưỡng.
- Replica lag vượt SLO.
- Disk utilization hoặc I/O latency tăng cao.
- Transaction lock wait tăng.
- Dung lượng còn lại không đủ cho bảng phụ và binlog.

Không đặt ngưỡng dựa trên một con số chung. Ngưỡng cần phản ánh tải bình thường, khả năng chịu tải của replica và mục tiêu độ trễ ứng dụng.

### 8.3. Cutover và metadata lock

Trước cutover:

1. Xác nhận copy hoàn tất và các thay đổi mới đã được áp dụng hết.
2. Kiểm tra replica lag và trạng thái công cụ.
3. Xác định session/transaction dài có thể giữ MDL.
4. Chọn thời điểm ít tải và thông báo cho bên vận hành/ứng dụng.
5. Đặt giới hạn thời gian chờ lock và theo dõi hàng đợi truy vấn.
6. Chỉ cho phép rename khi công cụ xác nhận dữ liệu đã đồng bộ.
7. Kiểm tra bảng sau cutover trước khi dọn bảng cũ.

Atomic rename giúp chuyển tên bảng trong một thao tác metadata, nhưng không có nghĩa không cần lock hoặc không có thời gian chờ. Nếu cutover không lấy được metadata lock, trì hoãn thường an toàn hơn việc buộc tiến trình tiếp tục khi chưa hiểu session đang giữ lock.

## 9. Kiểm tra sau migration và phương án phục hồi

Sau khi cutover, kiểm tra:

- `SHOW CREATE TABLE` cho biết schema mới đúng như mong muốn.
- Index, unique constraint, foreign key và trigger cần thiết vẫn tồn tại.
- Số lượng bản ghi và các aggregate quan trọng khớp với baseline.
- Các truy vấn đọc/ghi chính hoạt động và execution plan không suy giảm bất thường.
- Replica đã bắt kịp, không có lỗi applier và GTID/binlog tiếp tục tiến triển.
- Backup mới có thể chạy và quy trình PITR vẫn dùng được.
- Ứng dụng không còn truy cập nhầm cột hoặc giả định schema cũ.

Ví dụ kiểm tra cơ bản:

```sql
SHOW CREATE TABLE app.orders\G
SELECT COUNT(*) FROM app.orders;
SHOW INDEX FROM app.orders;
```

`COUNT(*)` trên bảng lớn có thể tốn tài nguyên; dùng cách đối chiếu phù hợp với yêu cầu và kích thước bảng, chẳng hạn thống kê theo khoảng khóa chính hoặc kiểm tra checksum theo chunk. Không coi số dòng bằng nhau là bằng chứng đầy đủ rằng mọi giá trị đã giống nhau.

### 9.1. Giữ bảng cũ và rollback

Sau cutover, công cụ có thể giữ bảng cũ trong một khoảng thời gian để hỗ trợ điều tra hoặc rollback. Tuy nhiên, nếu ứng dụng đã ghi dữ liệu mới vào bảng mới, bảng cũ sẽ nhanh chóng lỗi thời. Đổi tên ngược về bảng cũ có thể làm mất các giao dịch phát sinh sau cutover.

Vì vậy:

- Xác định rõ khoảng thời gian giữ bảng cũ và điều kiện xóa.
- Không xem bảng cũ là bản backup nhất quán sau khi hệ thống tiếp tục ghi.
- Nếu cần rollback dữ liệu, phải có kế hoạch đồng bộ ngược hoặc khôi phục từ backup/binlog.
- Kiểm tra disk trước khi giữ hai bản bảng lớn cùng lúc.
- Chỉ xóa bảng cũ sau khi ứng dụng, dữ liệu và replication đã được xác minh.

Rollback ứng dụng và rollback schema là hai việc khác nhau. Expand-contract giúp quay lại phiên bản ứng dụng cũ trong giai đoạn tương thích, còn thay đổi dữ liệu đã ghi sau cutover cần một chiến lược riêng.

## 10. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `ALTER TABLE` chờ lâu dù chọn `LOCK=NONE` | Đang chờ metadata lock ở giai đoạn bắt đầu/kết thúc | Tìm transaction giữ MDL, kiểm tra process list và giới hạn thời gian chờ |
| pt-osc không tạo được trigger | Thiếu quyền, trigger hiện hữu hoặc cấu trúc bảng không được hỗ trợ | Kiểm tra grant, trigger và phiên bản Percona Toolkit |
| pt-osc làm tăng latency ghi | Trigger đồng bộ thêm DML vào bảng phụ | Giảm chunk/load, theo dõi latency hoặc đánh giá phương pháp khác |
| Foreign key làm cutover kéo dài | Bảng con cần cập nhật constraint hoặc rebuild | Đánh giá phương thức FK và thử trên dữ liệu đại diện |
| gh-ost không đọc được binlog | Sai binlog format/row image, quyền hoặc nguồn binlog | Kiểm tra cấu hình, quyền replication và log retention |
| Migration bị thiếu sự kiện | Binlog đã purge trước khi công cụ đọc | Không cutover; đánh giá lại checkpoint và dựng lại migration |
| Replica lag tăng mạnh | Copy/apply tạo tải lớn hoặc replica không đủ năng lực | Throttle/pause, tăng thời gian migration và điều chỉnh tải |
| Không đủ dung lượng đĩa | Bảng phụ, binlog và temporary storage tăng đồng thời | Dừng có kiểm soát, giải phóng hoặc bổ sung dung lượng theo kế hoạch |
| Rollback bằng rename làm mất dữ liệu mới | Bảng cũ không nhận các ghi sau cutover | Khôi phục bằng backup/binlog hoặc đồng bộ dữ liệu theo kế hoạch |

## 11. Bài thực hành

Một bảng `app.orders` có 80 triệu dòng, InnoDB, primary key `id`, một số index phụ và hai bảng khác tham chiếu bằng foreign key. Ứng dụng có tải ghi đều cả ngày. Nhóm phát triển cần thêm cột `source_channel`, tạo index trên `created_at`, rồi đổi tên một cột cũ sau khi ứng dụng chuyển sang tên mới.

Hãy xây dựng kế hoạch migration:

1. Những thay đổi nào nên thử bằng native DDL trước? Bạn sẽ kiểm tra algorithm và lock bằng cách nào?
2. Nếu native DDL không đáp ứng thời gian hoặc mức khóa, pt-osc và gh-ost khác nhau ra sao về cơ chế đồng bộ?
3. Với hai bảng con có foreign key, cần điều tra những gì trước khi dùng pt-osc hoặc gh-ost?
4. Nếu dùng pt-osc, trigger ảnh hưởng thế nào đến latency ghi và quyền của tài khoản migration?
5. Nếu dùng gh-ost, cần xác minh `binlog_format`, `binlog_row_image`, `log_replica_updates` và retention như thế nào?
6. Đề xuất ngưỡng throttling dựa trên baseline CPU, `Threads_running`, disk I/O và replica lag.
7. Làm thế nào để tránh metadata lock bị giữ bởi transaction dài khi cutover?
8. Viết kế hoạch expand-contract cho việc đổi tên cột, gồm dual write, backfill, chuyển đọc và xóa cột cũ.
9. Nếu migration đã cutover và ứng dụng đã ghi dữ liệu mới, vì sao không thể đơn giản rename bảng cũ trở lại?
10. Nêu các kiểm tra schema, dữ liệu, execution plan, replication và backup sau migration.

Một kế hoạch tốt phải chỉ rõ công cụ, lý do chọn, dung lượng dự phòng, cách điều tiết, điều kiện cutover, thời gian giữ bảng cũ và tiêu chí dừng migration. Hãy diễn tập cả trường hợp copy bị dừng giữa chừng và cutover bị metadata lock chặn.

## Kết luận

Online schema change giúp thay đổi bảng lớn trong khi ứng dụng tiếp tục hoạt động phần lớn thời gian. Native online DDL nên được đánh giá trước vì ít thành phần vận hành; nếu cần bảng phụ, pt-online-schema-change dùng trigger để đồng bộ DML còn gh-ost đọc binary log để áp dụng thay đổi. Mọi phương pháp đều cần khóa chính phù hợp, ngân sách lưu trữ, kiểm soát tải và kế hoạch metadata-lock cutover. Kết hợp expand-contract, kiểm tra dữ liệu, giám sát replica và chiến lược rollback rõ ràng sẽ giúp migration có thể kiểm soát và phục hồi khi gặp sự cố.
