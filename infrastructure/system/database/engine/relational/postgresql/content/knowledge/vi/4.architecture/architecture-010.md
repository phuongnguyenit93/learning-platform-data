# Tiến trình nền mở rộng (background worker), autovacuum và tiến trình phục vụ sao chép

PostgreSQL không chỉ là một tiến trình nhận SQL rồi trả kết quả. Khi một instance hoạt động, hệ điều hành thường thấy **nhiều tiến trình** phối hợp với nhau: tiến trình chính quản lý vòng đời server, các backend phục vụ kết nối của ứng dụng, những tiến trình chuyên trách WAL và checkpoint, **autovacuum** thu gom phiên bản hàng cũ, cùng các tiến trình gửi/nhận WAL hoặc áp dụng thay đổi phục vụ sao chép dữ liệu.

Một số chức năng còn sử dụng cơ chế **background worker** (*tiến trình nền mở rộng*) để chạy công việc trong server mà không cần một kết nối người dùng thông thường. Hiểu các loại tiến trình này giúp trả lời những câu hỏi thực tế: vì sao bảng phình to dù đã xóa nhiều hàng, vì sao replica chậm hơn primary, vì sao tăng số truy vấn song song làm worker khan hiếm, và vì sao một lỗi trong thành phần nền có thể ảnh hưởng việc vận hành PostgreSQL.

Bài học tập trung vào ba nhóm của kiến trúc PostgreSQL:

1. **Background worker và các tiến trình nền của PostgreSQL:** chúng sinh ra, sử dụng tài nguyên và phối hợp với server như thế nào.
2. **Autovacuum:** launcher và worker tự động làm sạch dữ liệu theo MVCC, cập nhật thống kê và bảo vệ transaction ID.
3. **Tiến trình phục vụ sao chép:** WAL sender/receiver trong *physical replication*; logical replication launcher, apply worker và table synchronization worker trong *logical replication*.

Các ví dụ quan sát dùng SQL trong `psql`, đặc biệt là `pg_stat_activity`, `pg_stat_progress_vacuum`, `pg_stat_replication`, `pg_stat_wal_receiver` và `pg_stat_subscription`. Tên tiến trình và trường thống kê có thể khác theo phiên bản, nên những truy vấn này cần được áp dụng phù hợp với PostgreSQL đang vận hành.

> **Giới hạn thực hành:** Những câu `SELECT` trong bài chủ yếu để quan sát và có thể được thử trên một PostgreSQL được cấp quyền. Các thay đổi về autovacuum, worker limits, publication/subscription hay replication phải được thử trong lab hoặc triển khai theo quy trình phê duyệt. Không vô hiệu hóa autovacuum hoặc xóa replication slot tùy tiện trên production.

## 1. Bức tranh tổng thể: PostgreSQL là kiến trúc đa tiến trình

Trên các hệ thống phổ biến, PostgreSQL sử dụng **mô hình đa tiến trình**. Tiến trình chính thường được gọi là *postmaster* (tên chương trình `postgres`), điều phối việc khởi động, quản lý các tiến trình con và xử lý vòng đời server.

Khi client kết nối, PostgreSQL thông thường tạo một **backend process** cho connection đó. Bên cạnh backend còn có các tiến trình phục vụ công việc của toàn instance và các tiến trình theo nhu cầu như parallel worker hoặc logical replication worker.

Sơ đồ khái niệm:

```text
                 Client / Java / psql
                          │
                          ▼
               PostgreSQL main process
                    (postmaster)
                          │
            ┌─────────────┼──────────────────┐
            │             │                  │
            ▼             ▼                  ▼
      Client backends   Auxiliary       Background workers
      - SQL queries     processes       - Extension workers
      - Transactions    - Checkpointer  - Parallel workers
                        - WAL writer    - Logical apply/sync
                        - BG writer
                        - Autovacuum
                          launcher/worker
            │             │                  │
            └─────────────┼──────────────────┘
                          │
                          ▼
                Shared memory + WAL
                          │
          ┌───────────────┴─────────────────┐
          ▼                                 ▼
     WAL sender                        WAL receiver
     (primary / sender)                (standby)
          │                                 │
          └────────── WAL stream ───────────┘
```

Đây là sơ đồ **nhóm chức năng**, không phải cây cha–con chính xác của mọi process hay bản mô tả đầy đủ mọi luồng dữ liệu. Chẳng hạn trên standby, WAL receiver nhận WAL còn tiến trình *startup/recovery* thực hiện replay; trong logical replication, apply worker có vai trò riêng. Tùy cấu hình, một số tiến trình có thể **không tồn tại** khi chức năng tương ứng chưa bật.

### Các nhóm tiến trình nên phân biệt

| Nhóm | Vai trò chủ yếu | Thường được tạo khi nào? |
|---|---|---|
| **Main server/postmaster** | Khởi động và giám sát instance, nhận kết nối mới, điều phối tiến trình. | Khi PostgreSQL server start. |
| **Client backend** | Thực thi SQL, giữ trạng thái session và transaction cho connection. | Khi client kết nối thành công. |
| **Auxiliary processes** | Công việc hệ thống như checkpoint, WAL writing, background writing; phụ thuộc phiên bản và cấu hình. | Theo vòng đời server. |
| **Autovacuum launcher và workers** | Lập lịch và thực hiện vacuum/analyze tự động trên các bảng cần bảo trì. | Khi autovacuum hoạt động và có công việc đủ điều kiện. |
| **Generic/extension background workers** | Chạy tác vụ của core/extension mà không phải request SQL trực tiếp của client. | Khi extension hoặc cơ chế nội bộ đăng ký/yêu cầu worker. |
| **WAL sender** | Gửi dữ liệu thay đổi phục vụ streaming replication hoặc logical decoding. | Khi có kết nối replication tương ứng. |
| **WAL receiver** | Nhận WAL từ upstream trên standby vật lý. | Khi standby đang sử dụng streaming replication. |
| **Logical replication workers** | Đọc và áp dụng thay đổi theo subscription, đồng bộ bảng ban đầu. | Khi subscriber có subscription đang hoạt động. |

**Quan trọng:** Không nên gọi tất cả tiến trình nền là “background worker” theo nghĩa API mở rộng. PostgreSQL có nhiều **tiến trình nền lõi** với vai trò cố định; *background worker framework* là cơ chế cho các chức năng và extension đăng ký thêm tiến trình theo quản lý của server.

## 2. Vì sao PostgreSQL dùng tiến trình thay vì một tác vụ duy nhất?

Mỗi nhóm làm một loại công việc có đặc tính khác nhau. Backend truy vấn cần phản hồi nhanh cho ứng dụng; checkpointer cần phối hợp ghi trang bẩn; autovacuum làm việc nền định kỳ; replication cần gửi, nhận và áp dụng dữ liệu liên tục.

Tách thành các process mang lại một số lợi ích:

- **Cô lập công việc ở mức tiến trình:** một backend kết nối không trực tiếp là cùng một luồng thực thi với mọi backend khác.
- **Khả năng chạy đồng thời:** truy vấn của client, ghi WAL, vacuum và replication có thể tiến hành đồng thời theo tài nguyên và cơ chế đồng bộ.
- **Đơn vị giám sát rõ:** hệ điều hành và các view thống kê cho phép quan sát PID, loại backend, trạng thái, thời gian và nhiều sự kiện chờ.
- **Phân quyền và vòng đời có kiểm soát:** nhiều tiến trình được khởi tạo/quản lý bởi server chứ không do người dùng tùy ý tạo trong database.

Tuy nhiên, tách process **không có nghĩa chúng không ảnh hưởng nhau**. Chúng sử dụng bộ nhớ dùng chung, buffer cache, WAL, CPU, đĩa, network và tài nguyên khóa. Một autovacuum chạy trên bảng lớn có thể tiêu tốn I/O; replication worker bị chậm có thể giữ WAL qua replication slot; parallel workers có thể tranh nguồn lực với logical replication workers.

Vì vậy, khi quan sát PostgreSQL, phải xem cả **loại tiến trình** lẫn **tài nguyên mà nó đang cạnh tranh**.

## 3. Nhận diện tiến trình bằng pg_stat_activity

`pg_stat_activity` cung cấp thông tin về những tiến trình backend mà PostgreSQL đang theo dõi. Cột `backend_type` cho biết vai trò của từng dòng.

Ví dụ:

```sql
SELECT
    pid,
    backend_type,
    datname,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    backend_start
FROM pg_stat_activity
ORDER BY backend_type, pid;
```

Tùy phiên bản và thời điểm, bạn có thể thấy các loại như:

```text
client backend
autovacuum launcher
autovacuum worker
background writer
checkpointer
walwriter
walsender
walreceiver
logical replication launcher
logical replication worker
parallel worker
background worker
```

Danh sách trên là **ví dụ minh họa**, không phải cam kết mỗi server phải có đủ từng dòng hoặc tên hiển thị luôn giống hệt. Ví dụ một primary không có standby nối vào có thể không có WAL sender; một server chưa dùng logical replication có thể không có apply worker. Ngoài ra, khả năng nhìn thấy nội dung query/trạng thái của process thuộc người dùng khác còn phụ thuộc quyền quan sát.

### Một truy vấn tổng hợp số lượng theo loại

```sql
SELECT
    backend_type,
    COUNT(*) AS process_count
FROM pg_stat_activity
GROUP BY backend_type
ORDER BY process_count DESC, backend_type;
```

Truy vấn cho biết ảnh chụp tại thời điểm thực hiện, hữu ích khi muốn biết đang có bao nhiêu client backend, parallel worker hoặc autovacuum worker. **Một số tiến trình khởi tạo ngắn hạn có thể biến mất trước khi bạn quan sát**; ảnh chụp một thời điểm không đại diện cho toàn bộ hoạt động trong ngày.

### Nhận biết tiến trình đang chờ

```sql
SELECT
    pid,
    backend_type,
    state,
    wait_event_type,
    wait_event,
    now() - backend_start AS process_age
FROM pg_stat_activity
WHERE wait_event_type IS NOT NULL
ORDER BY backend_type, pid;
```

`wait_event_type`/`wait_event` giúp biết một process đang chờ loại sự kiện nào, ví dụ khóa, I/O hoặc hoạt động nội bộ. Nhưng **không phải mọi tiến trình có wait event đều đang gặp vấn đề**: một tiến trình nền có thể đang đợi công việc mới theo đúng thiết kế. Cần hiểu loại process và đối chiếu metric trước khi xử lý.

## 4. Background worker framework: cơ chế mở rộng tiến trình nền

PostgreSQL cung cấp cơ chế cho mã mở rộng (*extension*) hoặc thành phần core đăng ký **background workers**. Chúng chạy bên trong vòng đời PostgreSQL server, được quản lý bởi cơ chế của hệ thống và có thể thực hiện công việc theo lịch hoặc theo tín hiệu thay vì chờ một câu SQL trực tiếp từ client.

Một background worker có thể:

1. Khởi động từ lúc server start hoặc được đăng ký động ở thời điểm thích hợp.
2. Chạy một vòng lặp xử lý công việc/đợi tín hiệu.
3. Giao tiếp với server qua shared memory, latch hoặc cơ chế được PostgreSQL hỗ trợ.
4. Trong điều kiện API cho phép, kết nối tới database và thực hiện truy vấn qua **Server Programming Interface (SPI)**.
5. Kết thúc khi hoàn thành công việc, nhận tín hiệu shutdown hoặc khi server điều phối dừng.

Những thao tác này thuộc **API phía server**, thường yêu cầu mã C và hiểu sâu về mô hình tiến trình PostgreSQL. Một extension chạy background worker có mức độ tin cậy và quyền đặc biệt hơn nhiều so với một ứng dụng JDBC thông thường.

### Ví dụ ứng dụng

- Extension lập lịch tác vụ định kỳ, như những extension thực hiện công việc nền.
- Công việc theo dõi/thu thập chỉ số hoặc đồng bộ metadata trong server.
- Các worker nội bộ liên quan tới **parallel query**.
- Các worker phục vụ **logical replication** ở subscriber.

Không phải cứ có một tác vụ chạy theo lịch là background worker của PostgreSQL. Ví dụ Java scheduler ở một service riêng gọi `psql` hoặc JDBC là **process phía ứng dụng**, không tự biến thành PostgreSQL background worker.

### Static và dynamic registration

Một số extension yêu cầu cấu hình `shared_preload_libraries` để được nạp khi PostgreSQL khởi động và đăng ký worker từ sớm. Một số thành phần có thể đăng ký worker động nếu điều kiện API và quyền cho phép.

Việc thêm extension vào `shared_preload_libraries` không chỉ là thêm một tên vào file:

- Server phải tìm được shared library tương thích với đúng phiên bản PostgreSQL.
- Thư viện có thể chạy mã trong quá trình khởi động, nên lỗi cấu hình có thể khiến server không start được.
- Đổi `shared_preload_libraries` thường yêu cầu **restart**, không chỉ reload.
- Extension phải được rà soát độ tin cậy, phiên bản và kế hoạch rollback trước khi triển khai.

Đây là lý do background worker mở rộng thuộc phạm vi **quản trị hệ thống và code đáng tin cậy**, không phải tính năng để người dùng SQL tạo tiến trình tùy tiện.

## 5. Giới hạn tài nguyên cho background workers

Một số tham số ảnh hưởng khả năng chạy nhiều worker đồng thời:

| Tham số | Ý nghĩa điển hình | Điểm cần nhớ |
|---|---|---|
| `max_worker_processes` | Số lượng background worker processes mà PostgreSQL có thể hỗ trợ theo pool cấu hình. | Giới hạn năng lực cho các loại worker thuộc nhóm này; chỉ đổi lúc startup. |
| `max_parallel_workers` | Giới hạn số parallel workers thực sự có thể được dùng đồng thời trên instance. | Vẫn bị ràng buộc bởi các giới hạn worker khác và tài nguyên. |
| `max_parallel_workers_per_gather` | Giới hạn số parallel workers có thể được yêu cầu bởi một nút Gather/Gather Merge. | Không bảo đảm truy vấn luôn được cấp đủ worker. |
| `max_logical_replication_workers` | Giới hạn worker cho logical replication ở subscriber. | Các worker này còn chịu ảnh hưởng của `max_worker_processes`. |
| `max_sync_workers_per_subscription` | Số worker tối đa dùng cho đồng bộ bảng ban đầu của mỗi subscription. | Không nên nhầm với worker áp dụng luồng thay đổi thông thường. |
| `autovacuum_max_workers` | Giới hạn số autovacuum workers hoạt động đồng thời. | Là cơ chế điều tiết riêng của autovacuum, không nên đồng nhất trực tiếp với parallel-query worker limit. |
| `max_wal_senders` | Số WAL sender tối đa phục vụ các kết nối replication/sao lưu liên quan. | Giới hạn riêng cho tiến trình sender, không phải tên khác của `max_worker_processes`. |

Ví dụ quan sát cấu hình:

```sql
SELECT
    name,
    setting,
    unit,
    context,
    pending_restart
FROM pg_settings
WHERE name IN (
    'max_worker_processes',
    'max_parallel_workers',
    'max_parallel_workers_per_gather',
    'max_logical_replication_workers',
    'max_sync_workers_per_subscription',
    'autovacuum_max_workers',
    'max_wal_senders'
)
ORDER BY name;
```

`context` cho biết ngữ cảnh áp dụng tham số; một số tham số yêu cầu restart mới có hiệu lực. Không giả định mọi tham số có thể thay bằng `SET` trong session SQL.

**Ví dụ đánh đổi:** Nếu logical replication và extension nền cùng cần worker trong lúc truy vấn parallel cũng cần worker, pool chung có thể thành nút thắt. Khi thiếu worker, một số công việc bị trì hoãn hoặc truy vấn không chạy ở mức parallelism dự kiến. Tăng `max_worker_processes` có thể cần restart và tăng nhu cầu tài nguyên; không nên làm trước khi biết bottleneck thật.

## 6. Autovacuum tồn tại vì PostgreSQL sử dụng MVCC

PostgreSQL dùng **Multi-Version Concurrency Control (MVCC)** để cho phép các transaction đọc và ghi đồng thời theo quy tắc cô lập. Khi một hàng được `UPDATE`, PostgreSQL thường tạo **phiên bản hàng mới**; khi `DELETE`, phiên bản cũ không nhất thiết lập tức được xóa khỏi trang dữ liệu vì transaction khác có thể vẫn cần nhìn thấy nó.

Ví dụ:

```sql
CREATE TABLE demo_inventory (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    quantity INTEGER NOT NULL
);

INSERT INTO demo_inventory(sku, quantity)
VALUES ('SKU-001', 10);

UPDATE demo_inventory
SET quantity = 9
WHERE sku = 'SKU-001';

DELETE FROM demo_inventory
WHERE sku = 'SKU-001';
```

Sau những thay đổi ấy, PostgreSQL có thể còn các phiên bản tuple **không còn cần thiết đối với transaction nào** trong các heap pages. Những phiên bản này thường được gọi là **dead tuples** khi đã có thể thu hồi theo quy tắc MVCC.

`VACUUM` thông thường có thể:

- Xác định và thu hồi không gian của những phiên bản tuple cũ không còn cần thiết.
- Duy trì metadata liên quan đến index và visibility map để hỗ trợ truy cập hiệu quả.
- Thực hiện công việc **freezing transaction IDs** nhằm phòng ngừa transaction ID wraparound.
- Cập nhật một số thống kê lưu trữ liên quan.

`ANALYZE` có mục đích khác: thu thập **thống kê phân bố dữ liệu** để bộ tối ưu truy vấn chọn kế hoạch hợp lý. Autovacuum tự động có thể chạy cả công việc vacuum và autoanalyze, nhưng **VACUUM không thay thế hoàn toàn ANALYZE** trong mọi tình huống thống kê.

### VACUUM không đồng nghĩa trả hết dung lượng về hệ điều hành

Trong phần lớn trường hợp, `VACUUM` thông thường đánh dấu không gian trong bảng để **tái sử dụng cho dữ liệu mới**; file vật lý không nhất thiết co nhỏ lại ngay. Nó đôi khi có thể thu gọn các trang cuối file khi điều kiện cho phép, nhưng không phải lời hứa “xóa 1 GB dữ liệu là trả 1 GB dung lượng đĩa”.

`VACUUM FULL` có thể viết lại bảng để thu hồi không gian mạnh hơn nhưng đòi **khóa ACCESS EXCLUSIVE** và tài nguyên bổ sung. Đây không phải việc autovacuum thường xuyên tự động thực hiện.

## 7. Autovacuum launcher và autovacuum worker

PostgreSQL có hai vai trò rõ ràng:

| Thành phần | Vai trò |
|---|---|
| **Autovacuum launcher** | Thức dậy theo lịch/cơ chế lập lịch, xem xét các database và khởi tạo worker cho công việc phù hợp. |
| **Autovacuum worker** | Kết nối vào một database, chọn quan hệ cần bảo trì và thực hiện vacuum hoặc analyze tự động. |

Sơ đồ:

```text
       PostgreSQL server
              │
              ▼
     autovacuum launcher
              │
    định kỳ xét nhu cầu
              │
              ▼
    Khởi tạo autovacuum worker
              │
        ┌─────┴────────┐
        ▼              ▼
    Database A      Database B
    ├─ table X      └─ table Z
    └─ table Y
         │
         ▼
  VACUUM / ANALYZE khi đủ điều kiện
         │
         ▼
  Không gian tái sử dụng + thống kê
  + bảo vệ giới hạn tuổi XID
```

`autovacuum_naptime` ảnh hưởng chu kỳ launcher xem xét database, nhưng **không nên hiểu đây là cam kết “mỗi bảng được vacuum đúng mỗi N giây”**. Thực tế còn tùy ngưỡng, số worker, số database, tải I/O, tuổi transaction và thời gian công việc.

### Khi nào autovacuum được kích hoạt?

Đối với table thông thường, quyết định vacuum liên quan tới số lượng tuple cũ và số lượng hàng; một mô hình cơ bản:

\[
\text{Ngưỡng vacuum} \approx
\text{autovacuum\_vacuum\_threshold}
+
\text{autovacuum\_vacuum\_scale\_factor}
\times
\text{số hàng ước lượng}
\]

Giả sử ngưỡng cố định là **50**, hệ số là **0,2** và bảng khoảng **1.000.000 hàng**, ngưỡng theo mô hình đơn giản gần **200.050** dead tuples. Đây chỉ là phép tính giải thích ý nghĩa tham số, **không phải điều kiện duy nhất autovacuum dùng**.

PostgreSQL còn có những trigger khác như số hàng insert, tình trạng analyze và đặc biệt nhu cầu **freeze XID** để tránh wraparound. Cơ chế/thuật toán và các tham số bổ sung phụ thuộc phiên bản.

### Vì sao phải freeze transaction IDs?

PostgreSQL dùng transaction ID với không gian giá trị hữu hạn. Nếu các phiên bản tuple giữ XID quá cũ không được xử lý, hệ thống có nguy cơ **transaction ID wraparound** làm sai ý nghĩa thứ tự transaction.

Autovacuum có vai trò quan trọng trong việc **đóng băng thông tin transaction cũ** trước khi nguy cơ trở nên nghiêm trọng. Vì thế:

- Không nên tắt toàn bộ autovacuum chỉ để giảm I/O.
- Một số hoạt động chống wraparound có thể vẫn được PostgreSQL thực thi **ngay cả khi tắt autovacuum ở mức table**.
- Long-running transactions và replication slots giữ mốc XID cũ có thể cản trở thu hồi dead tuples.
- Nguy cơ wraparound có thể dẫn đến các cơ chế bảo vệ nghiêm ngặt, ảnh hưởng khả năng ghi của hệ thống.

**Autovacuum là thành phần đảm bảo sức khỏe lâu dài của dữ liệu**, không chỉ là tác vụ dọn rác giúp tiết kiệm đĩa.

## 8. Các tham số autovacuum cần biết

Một số cấu hình thường gặp:

| Tham số | Tác động |
|---|---|
| `autovacuum` | Bật/tắt cơ chế autovacuum thường quy theo quy tắc server. |
| `autovacuum_max_workers` | Giới hạn số autovacuum workers có thể hoạt động đồng thời. |
| `autovacuum_naptime` | Khoảng nghỉ/lập lịch cơ bản của launcher giữa các lần kiểm tra database. |
| `autovacuum_vacuum_threshold` | Thành phần ngưỡng số tuple cũ để cân nhắc vacuum. |
| `autovacuum_vacuum_scale_factor` | Phần tỷ lệ phụ thuộc kích thước bảng để cân nhắc vacuum. |
| `autovacuum_analyze_threshold` | Thành phần ngưỡng số thay đổi để cân nhắc autoanalyze. |
| `autovacuum_analyze_scale_factor` | Tỷ lệ thay đổi so với kích thước bảng dùng cho autoanalyze. |
| `autovacuum_vacuum_cost_delay` | Điều tiết nhịp làm việc nhằm giảm áp lực tài nguyên. |
| `autovacuum_vacuum_cost_limit` | Giới hạn chi phí trong cơ chế điều tiết vacuum. |
| `autovacuum_work_mem` | Giới hạn bộ nhớ có thể dùng cho công việc autovacuum, theo quy tắc tham số. |

Đọc giá trị thực tế:

```sql
SELECT
    name,
    setting,
    unit,
    context,
    pending_restart
FROM pg_settings
WHERE name LIKE 'autovacuum%'
ORDER BY name;
```

**Không sao chép các giá trị từ bài học vào production.** Thời gian thích hợp giữa các lần vacuum phụ thuộc tỷ lệ `UPDATE`/`DELETE`, kích thước bảng, HOT updates, index, storage, tải ứng dụng và giới hạn worker.

### Tinh chỉnh theo từng bảng

Một bảng nhận nhiều cập nhật có thể cần autovacuum sớm hơn phần còn lại. PostgreSQL hỗ trợ một số tham số lưu trong **table storage parameters**, ví dụ:

```sql
-- Chỉ minh họa trên bảng lab.
ALTER TABLE demo_inventory SET (
    autovacuum_vacuum_threshold = 1000,
    autovacuum_vacuum_scale_factor = 0.02
);
```

Thao tác này thay đổi điều kiện áp dụng cho bảng được chọn, không phải mọi bảng trong database. Tuy nhiên, **giảm ngưỡng không tự cấp thêm CPU hay I/O**. Nếu autovacuum workers luôn bận hoặc bị transaction lâu chặn thu hồi, cần điều tra nguyên nhân trước.

Để quay về cấu hình mặc định kế thừa từ server:

```sql
ALTER TABLE demo_inventory RESET (
    autovacuum_vacuum_threshold,
    autovacuum_vacuum_scale_factor
);
```

Lưu ý đây là DDL có thể cần quyền sở hữu bảng và có tác động khóa tương ứng; thực hiện thay đổi có kế hoạch thay vì trực tiếp chỉnh từng bảng không kiểm soát.

## 9. Quan sát autovacuum đang làm gì

### 9.1. Xem autovacuum worker qua pg_stat_activity

```sql
SELECT
    pid,
    backend_type,
    datname,
    state,
    wait_event_type,
    wait_event,
    query
FROM pg_stat_activity
WHERE backend_type IN ('autovacuum launcher', 'autovacuum worker')
ORDER BY backend_type, pid;
```

Nếu thấy một worker đang xử lý bảng lớn, đừng mặc định đó là tiến trình gây lỗi. Nó có thể đang làm công việc thiết yếu để tránh bloat hoặc wraparound.

### 9.2. Theo dõi tiến độ VACUUM

`pg_stat_progress_vacuum` cung cấp thông tin về **VACUUM đang hoạt động**, kể cả autovacuum workers trong những trường hợp phù hợp:

```sql
SELECT
    p.pid,
    p.datname,
    p.relid::regclass AS relation_name,
    p.phase,
    p.heap_blks_total,
    p.heap_blks_scanned,
    p.heap_blks_vacuumed,
    a.backend_type
FROM pg_stat_progress_vacuum AS p
LEFT JOIN pg_stat_activity AS a ON a.pid = p.pid
ORDER BY p.datname, p.pid;
```

Các `heap_blks_*` là **đơn vị khối/trang**, không phải số hàng. Tỷ lệ scanned/total giúp quan sát một giai đoạn, nhưng không phải luôn là phần trăm hoàn tất của toàn bộ VACUUM vì còn nhiều phase (quét heap, xử lý index, cleanup...).

Nếu truy vấn không trả hàng, nghĩa là không có VACUUM đang được thống kê ở thời điểm đó theo cơ chế view; **không chứng minh autovacuum đã bị tắt**.

### 9.3. Xem lịch sử gần đây và dead tuples ước lượng

```sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_autovacuum,
    autovacuum_count,
    last_autoanalyze,
    autoanalyze_count
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 20;
```

`n_live_tup` và `n_dead_tup` là **ước lượng thống kê**, không phải số đếm chính xác ngay tại từng thời điểm. `last_autovacuum` và các bộ đếm còn phụ thuộc thời điểm reset thống kê; bảng chưa có lần chạy đủ điều kiện có thể hiển thị giá trị null.

### 9.4. Phát hiện transaction tồn tại quá lâu

```sql
SELECT
    pid,
    usename,
    datname,
    state,
    now() - xact_start AS transaction_age,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start
LIMIT 20;
```

Một transaction mở quá lâu có thể giữ snapshot cũ và khiến vacuum chưa thể loại bỏ những phiên bản hàng đã chết đối với transaction đó. Khi thấy `idle in transaction` kéo dài, cần điều tra ứng dụng, connection pool và ranh giới commit/rollback.

**Không tự động `pg_terminate_backend(...)` đối với mọi session lâu**. Việc hủy một connection đang thực hiện nghiệp vụ có thể khiến rollback, lỗi người dùng hoặc trạng thái không rõ ở bên ngoài database.

## 10. Autovacuum, VACUUM thủ công và sự cạnh tranh tài nguyên

Đôi khi quản trị viên cần chạy `VACUUM` hoặc `ANALYZE` thủ công trong môi trường được ủy quyền:

```sql
VACUUM (ANALYZE) demo_inventory;
```

Lệnh vacuum thông thường không yêu cầu khóa độc quyền kiểu `VACUUM FULL` đối với mọi thao tác đọc/ghi, nhưng vẫn dùng CPU/I/O và có thể gặp cạnh tranh với DDL hoặc các hoạt động maintenance. Nó không phải thao tác hoàn toàn không tác động tới workload.

Một số điểm thực hành:

- `VACUUM` thông thường không chạy trong một **transaction block** tường minh.
- `ANALYZE` giúp cập nhật thống kê optimizer, có thể cần sau import lớn hoặc thay đổi phân bố.
- `VACUUM FULL` viết lại bảng, cần khóa mạnh, tạo gián đoạn và không phải cách khắc phục bloat mặc định.
- Nếu dead tuples tăng nhanh dù autovacuum chạy, hãy kiểm tra **long transactions, replication slot, ngưỡng, số worker, I/O và tần suất thay đổi dữ liệu**.
- Nếu lo ngại autovacuum gây tải, ưu tiên đo và điều tiết hợp lý thay vì tắt hẳn; tắt có thể khiến vấn đề bloat và XID nghiêm trọng hơn.

### Autovacuum “chậm” có thể là triệu chứng, không phải gốc bệnh

Giả sử hệ thống cập nhật cùng một bảng liên tục với tốc độ rất cao; autovacuum chạy gần như không nghỉ. Có thể cần:

1. Đánh giá `UPDATE` và chỉ mục: mỗi thay đổi có tạo nhiều phiên bản và cập nhật index không?
2. Kiểm tra transaction giữ snapshot cũ khiến dead tuples chưa được thu hồi.
3. Xem IO throughput, buffer cache và mức cạnh tranh.
4. Đánh giá ngưỡng vacuum và khả năng worker.
5. Xem lại thiết kế dữ liệu hoặc lịch xử lý, không chỉ tăng worker count.

Một cấu hình mạnh hơn giúp ích trong một số trường hợp, nhưng **không thay thế việc hiểu nguồn tạo dead tuples**.

## 11. Vai trò của WAL đối với sao chép PostgreSQL

**Write-Ahead Log (WAL)** ghi lại thông tin thay đổi cần thiết cho tính bền vững và phục hồi sự cố theo cơ chế PostgreSQL. Trước khi thay đổi trên trang dữ liệu được ghi bền vững, WAL thích hợp phải được ghi theo quy tắc của hệ thống.

WAL đồng thời là nền tảng cho nhiều cơ chế **replication**. Tuy nhiên, cần phân biệt hai hình thức:

| Đặc điểm | Physical replication | Logical replication |
|---|---|---|
| Dữ liệu truyền | WAL ở mức vật lý để tái hiện trạng thái cluster. | Luồng thay đổi logic được giải mã từ WAL theo publication/subscription. |
| Phạm vi | Thông thường theo **toàn cluster** PostgreSQL vật lý. | Theo **publication**, thường xác định tập bảng và thao tác được công bố. |
| Tiến trình nhận | Standby có **WAL receiver**, các tiến trình recovery replay WAL. | Subscriber có **logical replication apply worker** và có thể có table sync workers. |
| Mục tiêu phổ biến | Standby phục vụ HA, disaster recovery, có thể đọc trên hot standby. | Đồng bộ bảng giữa hệ thống, chuyển đổi dữ liệu/từng phần, tích hợp. |
| Khác biệt phiên bản/schema | Physical standby có ràng buộc tương thích rất chặt; không phải công cụ nâng cấp tùy ý. | Logical replication yêu cầu các bảng/kiểu dữ liệu/khóa và schema tương thích; không mặc nhiên sao chép mọi DDL. |

Không nên gọi một replica vật lý và một subscriber logic là cùng một thứ. Dù đều có thể sử dụng WAL sender trên publisher/upstream, **cách nhận và áp dụng thay đổi khác nhau**.

## 12. Physical streaming replication: WAL sender và WAL receiver

Trong streaming physical replication, một PostgreSQL primary tạo WAL và có thể gửi cho standby qua kết nối replication.

```text
 PRIMARY                                        STANDBY
─────────                                     ───────────
Client ghi SQL
     │
     ▼
Thay đổi dữ liệu + WAL
     │
     ▼
WAL sender  ─────── truyền WAL ───────────►  WAL receiver
                                                  │
                                                  ▼
                                               Ghi WAL
                                                  │
                                                  ▼
                                         Startup/recovery process
                                                  │
                                                  ▼
                                        Replay thay đổi lên dữ liệu
```

### WAL sender

Trên primary (hoặc standby upstream trong kiến trúc cascading replication), **WAL sender** phục vụ kết nối replication và gửi dữ liệu WAL phù hợp cho downstream. Khi có nhiều standby, có thể có nhiều WAL sender.

Một số tham số liên quan:

- `wal_level`: mức thông tin WAL được ghi, phải phù hợp mục đích replication.
- `max_wal_senders`: giới hạn số tiến trình WAL sender đồng thời.
- `max_replication_slots`: số replication slot có thể sử dụng.
- `wal_keep_size`: mức giữ WAL bổ trợ cho standby trong một số tình huống; không thay thế quy trình backup/PITR.
- `archive_mode` và `archive_command`: liên quan lưu WAL phục vụ archive/PITR và những chiến lược phục hồi khác.

Các tham số này có yêu cầu phiên bản và ngữ cảnh cấu hình riêng; một số đòi restart.

### WAL receiver

Trên standby vật lý, **WAL receiver** thiết lập kết nối đến nguồn, nhận WAL và lưu theo cơ chế của standby. Tiến trình recovery/startup **phát lại WAL** để dữ liệu trên standby tiến dần theo nguồn.

Phân biệt:

- **Đã nhận WAL** chưa chắc **đã replay** đến cùng LSN.
- **Đã replay WAL** chưa chắc ứng dụng đã có đủ quyền hoặc khả năng đọc tùy thiết lập standby.
- Một standby có thể không có WAL receiver tại một thời điểm nếu không còn kết nối streaming, nhưng vẫn có thể replay WAL đã có hoặc nhận log bằng cơ chế archive tùy cấu hình.

Vì vậy, quan sát WAL receiver cần kết hợp **tiến độ nhận, tiến độ phát lại và trạng thái kết nối**.

## 13. Theo dõi physical replication trên primary

Ở server có WAL sender đang phục vụ replication, `pg_stat_replication` cho thông tin về các kết nối sender:

```sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication
ORDER BY application_name, pid;
```

Ý nghĩa khái quát:

| Trường | Cách đọc |
|---|---|
| `pid` | PID của WAL sender phía server đang quan sát. |
| `application_name` | Tên ứng dụng của connection replication, thường dùng để nhận diện standby. |
| `client_addr` | Địa chỉ client replication khi có. |
| `state` | Trạng thái WAL sender, ví dụ đang streaming hay trong pha khác. |
| `sync_state` | Trạng thái đồng bộ của standby theo chính sách synchronous replication. |
| `sent_lsn` | Mốc WAL đã gửi. |
| `write_lsn` | Mốc downstream đã xác nhận ghi theo thông tin phản hồi. |
| `flush_lsn` | Mốc downstream đã xác nhận flush. |
| `replay_lsn` | Mốc downstream đã xác nhận replay. |

Các giá trị LSN mô tả **vị trí trong chuỗi WAL**, không phải số hàng hoặc số transaction. Khoảng cách LSN có thể được chuyển sang byte bằng hàm `pg_wal_lsn_diff`, nhưng số byte không tự biến thành số giây lag.

Ví dụ:

```sql
SELECT
    application_name,
    state,
    pg_wal_lsn_diff(sent_lsn, replay_lsn)
        AS sent_minus_replayed_bytes
FROM pg_stat_replication
WHERE sent_lsn IS NOT NULL
  AND replay_lsn IS NOT NULL;
```

Đây là phép so sánh **mốc gửi** và **mốc phát lại đã được báo về**, dùng để nhận diện backlog ở một thời điểm. Nếu muốn đánh giá RPO, cần biết chính sách đồng bộ, cơ chế commit và **mức bền vững thực sự** của WAL; một con số byte đơn lẻ chưa đủ để kết luận mức mất dữ liệu khi failover.

**Cẩn thận:** `pg_stat_replication` nằm ở phía **upstream gửi WAL**; không truy vấn view này trên một standby rồi coi tập kết quả rỗng là bằng chứng standby không nhận dữ liệu.

## 14. Theo dõi WAL receiver trên standby

Để xác định instance hiện tại có đang trong chế độ recovery/standby:

```sql
SELECT pg_is_in_recovery() AS is_standby;
```

Giá trị `true` cho biết server đang ở chế độ recovery, thường gặp trên standby vật lý. Sau đó xem WAL receiver:

```sql
SELECT
    pid,
    status,
    receive_start_lsn,
    latest_end_lsn,
    last_msg_send_time,
    last_msg_receipt_time,
    sender_host,
    sender_port
FROM pg_stat_wal_receiver;
```

Trong một số phiên bản PostgreSQL, danh sách cột và cách thống kê có thể khác; hãy kiểm tra view của đúng server nếu một cột không tồn tại.

Các hàm để kiểm tra tiến độ WAL trên standby:

```sql
SELECT
    pg_last_wal_receive_lsn() AS received_lsn,
    pg_last_wal_replay_lsn()  AS replayed_lsn,
    pg_last_xact_replay_timestamp() AS last_replayed_commit_time;
```

Và chênh lệch byte giữa WAL đã nhận và đã replay:

```sql
SELECT
    pg_wal_lsn_diff(
        pg_last_wal_receive_lsn(),
        pg_last_wal_replay_lsn()
    ) AS received_not_yet_replayed_bytes;
```

**Không lấy `now() - pg_last_xact_replay_timestamp()` làm lag tuyệt đối trong mọi hoàn cảnh.** Nếu primary không có transaction ghi mới, timestamp của transaction cuối được replay có thể cũ trong khi standby vẫn hoàn toàn bắt kịp. Cần kết hợp mốc WAL và tình hình có ghi mới ở primary.

### Phân biệt các loại chậm

```text
Primary tạo WAL
       │
       ▼
WAL sender gửi              → có thể chậm do mạng, sender, tải nguồn
       │
       ▼
WAL receiver nhận/ghi       → có thể chậm do mạng hoặc I/O standby
       │
       ▼
Standby flush WAL           → có thể chậm do lưu trữ
       │
       ▼
Standby replay WAL          → có thể chậm do replay, xung đột truy vấn,
                               I/O hoặc tác vụ khác
```

Một standby có kết nối streaming `status='streaming'` **vẫn có thể chậm**, vì trạng thái kết nối không thay thế đo tiến độ nhận và phát lại.

## 15. Logical replication: publisher, subscriber và background workers

Physical replication phục hồi các thay đổi vật lý ở mức cluster. Trong **logical replication**, PostgreSQL có thể giải mã WAL thành những thay đổi theo bảng và áp dụng trên một PostgreSQL khác.

Thuật ngữ:

- **Publisher:** server công bố những thay đổi của một hoặc nhiều bảng qua **publication**.
- **Subscriber:** server có **subscription**, nhận và áp dụng những thay đổi đã được công bố.
- **WAL sender/logical decoding:** ở phía publisher, gửi các thay đổi logic phù hợp với subscription.
- **Logical replication launcher:** ở subscriber, hỗ trợ quản lý/khởi tạo worker cần thiết cho subscriptions.
- **Apply worker:** ở subscriber, đọc stream và áp dụng thay đổi lên bảng đích.
- **Table synchronization worker:** hỗ trợ copy dữ liệu ban đầu của bảng khi subscription cần initial synchronization.

Sơ đồ:

```text
     PUBLISHER                               SUBSCRIBER
 ┌──────────────────┐                   ┌────────────────────────┐
 │ Bảng nguồn       │                   │ Bảng đích tương thích │
 │ INSERT/UPDATE/...│                   │                        │
 └─────────┬────────┘                   └────────────▲───────────┘
           │                                         │
           ▼                                         │
     WAL + decoding                                │
           │                                         │
           ▼                                         │
     WAL sender  ───────── logic stream ─────►  Apply worker
                                                     ▲
                                                     │
                                      Logical replication launcher
                                                     │
                                                     ▼
                                        Table sync worker (nếu cần
                                        đồng bộ dữ liệu ban đầu)
```

Logical replication hỗ trợ nhiều cách đồng bộ dữ liệu nhưng **không mặc định sao chép mọi đối tượng database**. Các thay đổi DDL/schema không tự được áp dụng như khi replay physical WAL; schema đích phải được quản lý tương thích. Một số loại đối tượng, sequence hoặc thao tác đặc biệt có cách xử lý riêng, cần xét theo phiên bản và thiết kế.

### Ví dụ cấu hình publication/subscription (chỉ mô tả)

Trên publisher có một bảng nghiệp vụ hợp lệ:

```sql
CREATE PUBLICATION sales_pub
FOR TABLE public.orders;
```

Trên subscriber đã có schema/bảng đích tương thích và role replication phù hợp:

```sql
-- Ví dụ cú pháp; KHÔNG chạy với tên host/tài khoản giả định.
CREATE SUBSCRIPTION sales_sub
CONNECTION 'host=publisher.example.internal port=5432 dbname=sales user=repl_user'
PUBLICATION sales_pub;
```

Lệnh tạo subscription có thể **kết nối tới publisher và tạo replication slot**, khởi động tiến trình đồng bộ; nó không đơn thuần lưu một dòng cấu hình. Cần chuẩn bị quyền, mạng, bảo mật, replication identity, table schema và dự phòng dung lượng WAL trước khi chạy.

**Không nhúng mật khẩu rõ vào migration, lịch sử shell hoặc bản tài liệu**. Quản lý credential bằng cơ chế bí mật/đăng nhập phù hợp với nền tảng.

## 16. Quan sát logical replication workers

Trên **subscriber**, trước tiên đọc `pg_stat_subscription`:

```sql
SELECT
    subname,
    pid,
    relid,
    received_lsn,
    latest_end_lsn,
    last_msg_send_time,
    last_msg_receipt_time,
    latest_end_time
FROM pg_stat_subscription
ORDER BY subname, pid;
```

Ý nghĩa:

- `subname`: tên subscription.
- `pid`: PID worker mà dòng thống kê mô tả, nếu đang có; có thể null khi worker không chạy.
- `relid`: có thể phân biệt worker đồng bộ bảng cụ thể trong ngữ cảnh phiên bản/cơ chế tương ứng.
- `received_lsn`, `latest_end_lsn` và timestamps: các mốc quan sát về quá trình nhận/áp dụng, không phải bảo đảm tất cả thao tác nghiệp vụ ngoài PostgreSQL đã đồng bộ.

Để nhìn các process liên quan:

```sql
SELECT
    pid,
    backend_type,
    application_name,
    state,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE backend_type LIKE '%logical replication%'
   OR backend_type = 'walsender'
ORDER BY backend_type, pid;
```

Ở publisher, `pg_stat_replication` cũng có thể hiển thị WAL sender của kết nối logical replication. Trên subscriber, các apply/sync workers chịu ảnh hưởng bởi `max_logical_replication_workers`, `max_sync_workers_per_subscription` và tổng capacity `max_worker_processes` theo cấu hình.

### Khi không thấy apply worker

Một subscription có thể ở trạng thái không hoạt động hoặc worker không chạy vì:

1. Subscription bị vô hiệu hóa theo cấu hình quản trị.
2. Subscriber chưa kết nối được publisher vì mạng, xác thực, quyền hoặc cấu hình.
3. Không đủ background worker slots.
4. Apply worker bị dừng bởi lỗi schema, kiểu dữ liệu, unique constraint hoặc lỗi khác.
5. Quá trình đồng bộ ban đầu hoặc việc áp dụng thay đổi có sự cố.

Cần đọc log **subscriber** trước tiên để tìm lỗi áp dụng; đồng thời kiểm tra WAL sender và slot ở publisher. Không kết luận subscriber thiếu tài nguyên chỉ vì không thấy PID trong một snapshot SQL.

## 17. Replication slots: vì sao worker chậm có thể làm đầy đĩa

Một **replication slot** lưu trạng thái cần thiết để PostgreSQL biết mức WAL hoặc dữ liệu mà consumer vẫn còn cần. Slots rất hữu ích để tránh xóa WAL quá sớm khi consumer tạm chậm hoặc ngắt kết nối, nhưng cũng tạo rủi ro **giữ WAL lâu**.

Trên server sở hữu slot:

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
ORDER BY slot_name;
```

| Cột | Ý nghĩa cơ bản |
|---|---|
| `slot_name` | Tên slot. |
| `slot_type` | `physical` hoặc `logical`. |
| `active` | Hiện có consumer sử dụng slot theo thông tin PostgreSQL hay không. |
| `restart_lsn` | Mốc WAL cũ nhất mà slot có thể còn cần giữ. |
| `confirmed_flush_lsn` | Mốc đã được xác nhận xử lý theo semantics của logical slot; thường không áp dụng cho physical slot. |

Bạn có thể dùng `pg_wal_lsn_diff` để ước lượng khoảng WAL tính bằng byte từ mốc hiện tại tới mốc giữ:

```sql
SELECT
    slot_name,
    slot_type,
    active,
    pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)
        AS wal_distance_bytes
FROM pg_replication_slots
WHERE restart_lsn IS NOT NULL;
```

Ví dụ trên dùng `pg_current_wal_lsn()` trên **primary**; không áp dụng máy móc trên standby đang recovery. Khoảng LSN là phép đo **khoảng cách WAL**, không nhất thiết bằng đúng dung lượng filesystem đang bị giữ lại riêng cho slot, do segment boundary, checkpoint, cấu hình retention và các consumer khác.

### Vì sao không xóa slot khi thấy inactive?

`active = false` chỉ cho biết consumer không dùng slot ở thời điểm quan sát. Một subscriber có thể đang ngừng để bảo trì. Nếu xóa slot, downstream có thể **không còn khả năng bắt kịp bằng stream cũ** và phải đồng bộ/khởi tạo lại.

Quy trình an toàn:

1. Xác định **ai sở hữu slot** và consumer nào cần nó.
2. Kiểm tra trạng thái subscription/standby và lịch bảo trì.
3. Đo WAL đang giữ, tốc độ tăng, dung lượng còn trống, ngưỡng cảnh báo.
4. Điều tra nguyên nhân consumer chậm hoặc ngắt.
5. Chỉ thay đổi/drop slot theo runbook được duyệt, có phương án xây lại consumer.

Tham số như `max_slot_wal_keep_size` có thể giúp giới hạn khả năng giữ WAL của slot theo điều kiện/phiên bản, nhưng nếu ngưỡng bị vượt và WAL cần thiết không còn, consumer có thể phải được khởi tạo lại. Không xem giới hạn này là biện pháp hoàn toàn không có tác dụng phụ.

## 18. Autovacuum và replication có liên hệ gì?

Thoạt nhìn autovacuum chỉ xử lý dead tuples, còn replication chỉ gửi nhận WAL. Thực tế, chúng tác động lẫn nhau.

### 18.1. Autovacuum tạo WAL và sử dụng I/O

Hoạt động vacuum có thể sinh WAL cho những thay đổi metadata/trang cần thiết, đồng thời tiêu thụ CPU và I/O. Trên primary, WAL tạo ra cũng có thể ảnh hưởng tải gửi và replay trên standby. Nếu hệ thống bận, replication workers và autovacuum có thể tranh tài nguyên lưu trữ.

**Không nên suy ra “vacuum luôn là nguyên nhân replication lag”** chỉ vì hai hoạt động xảy ra đồng thời. Phải đo lưu lượng WAL, I/O, LSN và wait events.

### 18.2. Replication slots có thể giữ mốc XID

Một số replication slots, đặc biệt logical slots, có thể duy trì `xmin` hoặc `catalog_xmin` để bảo vệ các phiên bản tuple/catalog mà logical decoding còn cần. Nếu consumer bị đình trệ, việc giữ snapshot hoặc mốc XID cũ có thể cản trở thu hồi dữ liệu chết, góp phần gây **table/catalog bloat**.

Có thể quan sát những cột liên quan tùy phiên bản:

```sql
SELECT
    slot_name,
    slot_type,
    active,
    xmin,
    catalog_xmin
FROM pg_replication_slots
ORDER BY slot_name;
```

Giá trị null không tự động nghĩa là slot không có bất kỳ tác động retention nào; còn cần xem `restart_lsn` và cấu hình.

### 18.3. Transaction dài gây khó khăn cho vacuum và ứng dụng

Một transaction đọc lâu giữ snapshot cũ có thể ngăn vacuum thu hồi tuple. Trên hot standby, các truy vấn chạy lâu cũng có thể xung đột với việc replay một số WAL records, tùy cấu hình quản lý conflict và replication feedback.

Ví dụ một standby được cấu hình feedback nhằm giảm query cancellation có thể làm primary giữ thêm phiên bản dữ liệu, khiến bloat tăng. Đây là **đánh đổi giữa trải nghiệm truy vấn standby và khả năng thu hồi dữ liệu ở primary**, không có cấu hình đơn giản đúng cho mọi hệ thống.

## 19. Nhìn toàn cảnh các tiến trình nền qua tình huống thực tế

### Tình huống A — PostgreSQL dùng nhiều CPU dù không có request SQL lớn

Quan sát `pg_stat_activity` cho thấy nhiều `autovacuum worker` đang hoạt động. Một bảng có `n_dead_tup` lớn và `last_autovacuum` gần thời điểm hiện tại.

**Cách tiếp cận:** xem `pg_stat_progress_vacuum`, transaction dài, tốc độ update/delete, I/O và ngưỡng worker. Không dừng mọi autovacuum chỉ vì CPU tăng; trước hết xác định đây là bảo trì cần thiết hay do thay đổi workload.

### Tình huống B — Replica streaming nhưng dữ liệu đọc chậm hơn primary

`pg_stat_replication.state` báo `streaming`, nhưng `replay_lsn` cách xa `sent_lsn`.

**Cách tiếp cận:** kiểm tra WAL receiver, chênh lệch nhận–replay, I/O standby, truy vấn dài và xung đột replay. Một kết nối streaming còn sống không bảo đảm dữ liệu đã replay kịp.

### Tình huống C — Logical subscription bị đứng sau thay đổi schema

Trên publisher có thay đổi bảng hoặc kiểu dữ liệu, subscriber không được cập nhật tương thích. Apply worker gặp lỗi và subscription không tiến triển.

**Cách tiếp cận:** xem log subscriber và `pg_stat_subscription`, so sánh schema nguồn/đích, không xóa slot chỉ để “reset lag”. Phải giải quyết lỗi áp dụng hoặc có kế hoạch đồng bộ lại rõ ràng.

### Tình huống D — Disk pg_wal tăng khi consumer mất kết nối

Một logical slot ở trạng thái `active=false`, `restart_lsn` cách xa WAL hiện tại; dung lượng WAL tăng nhanh.

**Cách tiếp cận:** xác định consumer, kiểm tra còn cần slot không, khôi phục khả năng tiêu thụ hoặc quyết định khởi tạo lại theo chính sách. Không tự drop slot khi chưa biết hệ quả mất dữ liệu cho downstream.

### Tình huống E — Truy vấn parallel chậm và logical replication cũng có backlog

Một extension nền và các logical replication workers sử dụng worker pool; truy vấn SQL không nhận được mức parallelism dự kiến.

**Cách tiếp cận:** kiểm tra `max_worker_processes`, `max_parallel_workers`, `max_logical_replication_workers`, các tiến trình thực tế và tài nguyên host. Không tăng tất cả giới hạn cùng lúc khi chưa biết có đủ CPU/RAM/I/O hay không.

## 20. Quy trình giám sát cho người vận hành

Một runbook quan sát cơ bản có thể đi theo thứ tự:

```text
1. Server và các tiến trình đang tồn tại?
          │
          ▼
   pg_stat_activity.backend_type
          │
          ▼
2. Autovacuum có bắt kịp thay đổi dữ liệu?
          │
          ▼
   pg_stat_user_tables + pg_stat_progress_vacuum
          │
          ▼
3. WAL sender/receiver có hoạt động và theo kịp?
          │
          ▼
   pg_stat_replication (sender)
   pg_stat_wal_receiver (standby)
   pg_last_wal_receive/replay_lsn (standby)
          │
          ▼
4. Logical apply workers và slots có bị tắc?
          │
          ▼
   pg_stat_subscription + pg_replication_slots
          │
          ▼
5. Tìm nguyên nhân gốc:
   - long transactions / locks
   - schema conflicts
   - worker limits
   - CPU, I/O, network
   - WAL retention and disk space
          │
          ▼
6. Thay đổi theo runbook, đo lại và lưu bằng chứng
```

### Những nguyên tắc theo dõi cần nhớ

- **Một ảnh chụp tức thời không phải xu hướng.** Thu thập metric theo thời gian để thấy số worker, dead tuples, WAL lag và dung lượng tăng hay giảm.
- **Các view thống kê có độ trễ và giới hạn quyền.** Một số trường là ước lượng hoặc có thể null. Phân biệt “không có dữ liệu” với “tình trạng bằng không”.
- **Không đánh đồng kết nối sống với dữ liệu đồng bộ.** Với replication, đo nhận, flush và replay theo ngữ cảnh.
- **Không đánh đồng worker hiện diện với sự cố.** Autovacuum chạy lâu có thể đang cần thiết; replication sender ở trạng thái chờ có thể bình thường khi không có WAL mới.
- **Không thay đổi nhiều tham số cùng lúc.** Đo trước/sau, xác định rollback, và cập nhật cấu hình bền vững nếu thay đổi cần duy trì qua restart.
- **Không chạy lệnh phá hủy để thử xử lý lỗi.** Drop slot, kill process, tắt autovacuum hoặc restart trong môi trường HA đều cần biết rõ ảnh hưởng.

## 21. Bài tập thực hành

### Bài 1 — Phân loại các tiến trình

Cho một danh sách `backend_type` gồm `client backend`, `autovacuum launcher`, `autovacuum worker`, `walsender`, `walreceiver`, `logical replication worker`, `parallel worker` và `checkpointer`.

Hãy chia thành nhóm phục vụ truy vấn người dùng, bảo trì dữ liệu, sao chép và công việc lõi khác. Giải thích vì sao không nên gọi tất cả các tiến trình ấy là “extension background workers”.

### Bài 2 — Quan sát bằng SQL

Viết truy vấn `pg_stat_activity` trả `pid`, `backend_type`, `state` và `wait_event` của các tiến trình nền. Viết thêm một truy vấn đếm số process theo `backend_type`. Giải thích vì sao một lần query không thấy autovacuum worker chưa đủ kết luận autovacuum đã tắt.

### Bài 3 — Tính ngưỡng autovacuum

Giả sử một bảng có 2.000.000 hàng, `autovacuum_vacuum_threshold=100` và `autovacuum_vacuum_scale_factor=0.05`. Theo công thức đơn giản về dead tuples, ngưỡng là bao nhiêu?

*Gợi ý:* `100 + 0,05 × 2.000.000 = 100.100` dead tuples. Nêu ít nhất hai tình huống khác khiến công việc autovacuum được kích hoạt hoặc bị ảnh hưởng.

### Bài 4 — Autovacuum không thu hồi được dead tuples

`n_dead_tup` tăng đều, autovacuum đã chạy nhưng dung lượng bảng tiếp tục phình. Đồng thời có nhiều `idle in transaction` kéo dài và một logical replication slot bị chậm.

Hãy mô tả cách kiểm tra transaction age, `pg_replication_slots.xmin`/`catalog_xmin`, các chỉ số vacuum, và vì sao việc tăng `autovacuum_max_workers` đơn thuần có thể không giải quyết nguyên nhân gốc.

### Bài 5 — Chẩn đoán replication lag

Trên primary, `sent_lsn` tiếp tục tăng; trên standby, `pg_last_wal_receive_lsn()` gần mốc gửi nhưng `pg_last_wal_replay_lsn()` ở phía sau đáng kể.

Theo sơ đồ sender → receiver → replay, bạn sẽ ưu tiên kiểm tra bước nào? Hãy nêu ví dụ những nguyên nhân liên quan I/O, replay và truy vấn dài trên standby.

### Bài 6 — Logical replication không có apply worker

Một subscription đã được tạo nhưng `pg_stat_subscription` không thấy worker áp dụng đang hoạt động. Hãy đề xuất quy trình kiểm tra từ trạng thái subscription, quyền/kết nối, log subscriber, worker limits cho đến slot phía publisher. Vì sao không nên drop slot ngay?

### Bài 7 — Giới hạn background workers

Hệ thống dùng extension background worker, logical replication và parallel query. Hãy giải thích sự khác nhau giữa `max_worker_processes`, `max_logical_replication_workers` và `max_parallel_workers`. Liệt kê các chỉ số cần quan sát trước khi tăng cấu hình.

### Bài 8 — Lập một dashboard tối thiểu

Thiết kế dashboard theo dõi PostgreSQL với các nhóm:

- Số tiến trình theo `backend_type`.
- Số dead tuples ước lượng và thời điểm autovacuum/autoanalyze của bảng nóng.
- Tiến độ `pg_stat_progress_vacuum` khi có.
- WAL sent/received/replayed LSN và độ trễ.
- Trạng thái logical subscription và replication slots đang giữ WAL.
- Dung lượng filesystem/WAL, CPU, I/O và long-running transactions.

Hãy giải thích cách dùng dữ liệu nhiều thời điểm để phân biệt tình trạng bình thường với sự cố.

## Kết luận

Kiến trúc PostgreSQL gồm **nhiều tiến trình có nhiệm vụ riêng**. Backend phục vụ SQL; các tiến trình lõi thực hiện công việc lưu trữ, WAL và checkpoint; cơ chế **background worker** cho phép core và extension chạy tác vụ được server quản lý. **Autovacuum launcher và workers** giữ vai trò bảo trì thiết yếu trong thế giới MVCC: thu hồi dead tuples có thể tái sử dụng, cập nhật thống kê và phòng ngừa XID wraparound.

Trong sao chép dữ liệu, **WAL sender** ở phía gửi và **WAL receiver cùng recovery process** ở standby tạo nên đường physical streaming. Với **logical replication**, publisher cung cấp luồng thay đổi còn subscriber sử dụng **logical replication launcher, apply worker và table synchronization worker** để đồng bộ dữ liệu theo publication/subscription.

Để vận hành an toàn, hãy kết hợp quan sát **`pg_stat_activity`, `pg_stat_user_tables`, `pg_stat_progress_vacuum`, `pg_stat_replication`, `pg_stat_wal_receiver`, `pg_stat_subscription` và `pg_replication_slots`**. Không đánh giá một tiến trình chỉ qua tên hoặc một thời điểm: phải hiểu cơ chế, đo mức tiến triển và tài nguyên, rồi mới điều chỉnh worker limits, autovacuum hoặc replication theo quy trình kiểm soát.
