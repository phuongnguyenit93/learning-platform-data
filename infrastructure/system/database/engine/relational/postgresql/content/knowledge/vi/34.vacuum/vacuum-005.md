# Autovacuum worker, giới hạn chi phí và tốc độ dọn dẹp trong PostgreSQL

PostgreSQL tạo ra các phiên bản tuple mới khi UPDATE và đánh dấu các phiên bản cũ không còn cần thiết sau khi những transaction phù hợp kết thúc. DELETE cũng để lại dead tuples cần được thu hồi. Nếu không có cơ chế dọn dẹp, bảng và index có thể phình to, query phải đọc nhiều page hơn, visibility map kém hiệu quả và transaction ID có nguy cơ tiến gần wraparound.

**Autovacuum** là cơ chế nền tự động thực hiện VACUUM và ANALYZE khi thống kê cho thấy một relation cần bảo trì. Nhưng autovacuum không chạy vô hạn tốc độ. Nó có launcher, số worker đồng thời, ngưỡng kích hoạt, giới hạn chi phí I/O, bộ nhớ và các giới hạn do transaction lâu dài.

Một cấu hình tốt phải cân bằng ba mục tiêu:

- Dọn dead tuples đủ sớm để tránh table/index bloat.
- Giữ thống kê planner đủ mới để chọn execution plan phù hợp.
- Không để hoạt động bảo trì chiếm hết CPU, I/O, memory hoặc connection resources của workload ứng dụng.

~~~mermaid
flowchart TD
    L["Autovacuum launcher"] --> S["Quét database theo chu kỳ"]
    S --> Q["Xét threshold và thống kê relation"]
    Q -->|"Đủ điều kiện"| W["Autovacuum worker"]
    Q -->|"Chưa đủ điều kiện"| N["Chờ chu kỳ tiếp"]
    W --> V["VACUUM: dead tuples, visibility map, freeze"]
    W --> A["ANALYZE: cập nhật planner statistics"]
    V --> C["Cost accounting"]
    A --> C
    C --> D["Cost limit đạt ngưỡng?"]
    D -->|"Có"| T["Cost delay / sleep"]
    D -->|"Chưa"| V
    T --> V
~~~

Bài học thuộc chương **VACUUM**, module **Database Engine Relational PostgreSQL**. Chúng ta sẽ tìm hiểu launcher/worker, công thức threshold, cost-based throttling, cấu hình theo từng bảng, chống transaction ID wraparound và cách giám sát tốc độ dọn dẹp bằng catalog/statistics.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vai trò của autovacuum launcher và autovacuum worker.
2. Phân biệt VACUUM, ANALYZE và autovacuum.
3. Hiểu vì sao track_counts cần được bật để autovacuum hoạt động đúng.
4. Tính ngưỡng vacuum/analyze dựa trên threshold và scale factor.
5. Phân biệt vacuum do UPDATE/DELETE với vacuum do INSERT.
6. Hiểu autovacuum_naptime, autovacuum_max_workers và giới hạn worker.
7. Giải thích cost-based vacuum delay, cost limit và các loại page cost.
8. Biết vì sao tăng số worker không đồng nghĩa tốc độ dọn dẹp tăng tuyến tính.
9. Điều chỉnh autovacuum theo từng bảng bằng storage parameters.
10. Quản lý autovacuum_work_mem và tác động bộ nhớ của nhiều worker.
11. Nhận diện anti-wraparound vacuum và vì sao không nên tắt cơ chế này.
12. Hiểu long-running transaction, replication slot và standby feedback có thể chặn cleanup.
13. Giám sát bằng pg_stat_user_tables, pg_stat_progress_vacuum, pg_stat_activity và catalog.
14. Chẩn đoán autovacuum chạy chậm, không chạy hoặc backlog tăng.
15. Thiết kế tuning theo workload thay vì sao chép một cấu hình cho mọi database.

## 2. VACUUM, ANALYZE và autovacuum khác nhau thế nào?

| Cơ chế | Mục tiêu | Kết quả chính |
| --- | --- | --- |
| `VACUUM` | Thu hồi dead tuples có thể dọn | Cho phép tái sử dụng space, cập nhật visibility/freeze metadata |
| `ANALYZE` | Lấy mẫu dữ liệu và cập nhật thống kê | Planner ước lượng cardinality/selectivity tốt hơn |
| `autovacuum` | Tự động quyết định khi nào chạy vacuum/analyze | Bảo trì nền theo ngưỡng và thống kê |
| `VACUUM FULL` | Rewrite/compact relation | Có thể trả space về filesystem, cần lock mạnh |

Autovacuum worker có thể thực hiện VACUUM và ANALYZE cho một relation tùy điều kiện. Hai công việc có ngưỡng kích hoạt riêng:

- Dead tuples/insert activity có thể làm relation đủ điều kiện VACUUM.
- Số row modifications từ lần ANALYZE gần nhất có thể làm relation đủ điều kiện ANALYZE.

**Autovacuum không phải VACUUM FULL chạy tự động.** Vacuum thông thường chủ yếu làm space có thể tái sử dụng trong relation và hỗ trợ visibility map; nó không mặc định compact toàn bộ file để trả dung lượng cho hệ điều hành.

## 3. Vì sao cần autovacuum?

PostgreSQL sử dụng MVCC. Khi UPDATE một hàng, hệ thống thường tạo tuple version mới; phiên bản cũ trở thành dead tuple khi không còn snapshot nào cần nó. DELETE cũng làm row trở thành không còn visible với các transaction mới, nhưng physical storage không nhất thiết biến mất ngay lập tức.

Ví dụ:

~~~sql
UPDATE orders
SET status = 'paid'
WHERE order_id = 100;
~~~

Về mặt logic, ứng dụng thấy một row đổi trạng thái. Về mặt storage, PostgreSQL có thể có:

- Tuple version cũ.
- Tuple version mới.
- Index entries liên quan.
- Metadata visibility và transaction ID.

Sau nhiều lần UPDATE/DELETE, nếu không vacuum:

- Heap chứa nhiều dead tuples.
- Index cần cleanup dead entries.
- Table scan đọc thêm page.
- Planner statistics có thể cũ.
- Dung lượng relation có thể tăng.
- Transaction ID freezing có thể bị trì hoãn.

Autovacuum giúp xử lý phần lớn bảo trì thường xuyên mà DBA không cần tự lên lịch VACUUM cho từng bảng.

## 4. Kiến trúc launcher và worker

Autovacuum gồm hai vai trò chính:

**Autovacuum launcher**

- Là tiến trình nền điều phối.
- Theo chu kỳ kiểm tra database trong cluster.
- Khởi chạy worker khi có slot và công việc phù hợp.
- Phân phối hoạt động giữa các database theo autovacuum_naptime.

**Autovacuum worker**

- Kết nối vào một database được giao.
- Xem xét các relation đủ điều kiện vacuum/analyze.
- Thực hiện công việc bảo trì theo threshold và cost settings.
- Ghi thống kê/log theo cấu hình.

~~~text
PostgreSQL cluster
  |
  +-- Autovacuum launcher
        |
        +-- Worker 1 -> database A -> table orders
        |
        +-- Worker 2 -> database B -> table events
        |
        +-- Worker 3 -> database A -> table sessions
~~~

Sơ đồ chỉ minh họa các worker hoạt động đồng thời. Mỗi worker có workload và thời gian riêng; không nên hiểu autovacuum_max_workers = 3 là ba worker luôn chạy hoặc mỗi bảng luôn có ba worker vacuum song song.

### Một worker có làm nhiều bảng cùng lúc?

Một autovacuum worker thực hiện bảo trì relation theo trình tự trong database được giao. autovacuum_max_workers giới hạn số worker đồng thời trong cluster, giúp nhiều relation/database có thể được xử lý song song. Tăng giá trị này không tự chia một lần vacuum của một bảng thành nhiều worker độc lập.

## 5. Điều kiện để autovacuum hoạt động

Cấu hình quan trọng:

~~~conf
autovacuum = on
track_counts = on
~~~

track_counts cần được bật để PostgreSQL thu thập thống kê hoạt động của bảng phục vụ quyết định autovacuum. Nếu tắt, cơ chế tự động không có dữ liệu thống kê cần thiết để hoạt động đúng.

Ngoài ra cần xét:

- Database có relation cần bảo trì.
- Table-level options có thể override global settings.
- Worker slots có sẵn.
- Worker có thể lấy lock phù hợp.
- Transaction snapshots không chặn cleanup.
- Autovacuum launcher và worker không bị vô hiệu hóa bởi cấu hình/quyền vận hành.

### Autovacuum off có tắt mọi vacuum chống wraparound không?

Không nên hiểu như vậy. PostgreSQL vẫn có thể khởi chạy autovacuum worker đặc biệt để ngăn transaction ID wraparound ngay cả khi autovacuum thường bị tắt. Đây là cơ chế an toàn hệ thống quan trọng.

Tuy nhiên, tắt autovacuum thường vẫn rất nguy hiểm vì dead tuples, analyze statistics và insert-triggered vacuum có thể bị bỏ mặc trong thời gian dài.

## 6. Threshold và scale factor

Autovacuum không vacuum mọi bảng sau mỗi INSERT/UPDATE/DELETE. Nó dùng ngưỡng gồm một phần cố định và một phần tỷ lệ theo kích thước relation.

### Ngưỡng vacuum do UPDATE/DELETE

Công thức khái quát:

~~~text
vacuum threshold =
    autovacuum_vacuum_threshold
    + autovacuum_vacuum_scale_factor * reltuples
~~~

Trong đó:

- autovacuum_vacuum_threshold: số dead tuples cơ sở.
- autovacuum_vacuum_scale_factor: tỷ lệ theo số tuples ước lượng của bảng.
- reltuples: ước lượng row count trong catalog, không phải số đếm chính xác realtime.

Ví dụ với giá trị mặc định thường gặp:

~~~text
autovacuum_vacuum_threshold = 50
autovacuum_vacuum_scale_factor = 0.20
reltuples = 1,000,000

threshold = 50 + 0.20 * 1,000,000
          = 200,050 dead tuples
~~~

Nếu bảng có 100 triệu rows, threshold theo công thức tương tự có thể lên tới khoảng 20 triệu dead tuples. Đây là lý do một scale factor phù hợp cho bảng nhỏ có thể quá lỏng với bảng rất lớn.

**Các giá trị mặc định có thể thay đổi theo major version hoặc distribution.** Hãy đọc pg_settings trên server thực tế trước khi tuning.

### Ngưỡng ANALYZE

Công thức khái quát:

~~~text
analyze threshold =
    autovacuum_analyze_threshold
    + autovacuum_analyze_scale_factor * reltuples
~~~

ANALYZE được kích hoạt theo số row modifications kể từ lần analyze gần nhất. Nó không đợi dead tuples đạt vacuum threshold.

Ví dụ:

- Bảng 1 triệu rows.
- Base threshold 50.
- Analyze scale factor 0.10.

Ngưỡng ước lượng là 100.050 modifications. Khi workload cập nhật phân bố dữ liệu rất nhanh, có thể cần analyze thường xuyên hơn để planner có thống kê mới.

### Threshold là ước lượng, không phải lịch chạy chính xác

Autovacuum dùng statistics và scheduling cycle. Không nên kỳ vọng worker bắt đầu đúng tại thời điểm row count vừa vượt ngưỡng. Còn có launcher cadence, worker availability, relation eligibility và lock conditions.

## 7. Vacuum do INSERT

Một bảng append-only có thể hầu như không có dead tuples do UPDATE/DELETE nhưng vẫn cần vacuum.

PostgreSQL có các tham số:

- autovacuum_vacuum_insert_threshold
- autovacuum_vacuum_insert_scale_factor

Công thức khái quát:

~~~text
insert vacuum threshold =
    autovacuum_vacuum_insert_threshold
    + autovacuum_vacuum_insert_scale_factor * reltuples
~~~

Vacuum do INSERT giúp xử lý các page mới, bao gồm cập nhật visibility map và freezing phù hợp. Điều này có thể hỗ trợ index-only scans và quản lý transaction IDs.

### Vì sao insert-only table vẫn cần vacuum?

Một table time-series có thể chỉ INSERT hàng triệu events. Nếu không có vacuum phù hợp:

- Page mới có thể chưa được đánh dấu all-visible.
- Index-only scan có thể phải truy cập heap nhiều hơn.
- Tuổi transaction ID của tuples cần được quản lý.
- Visibility/freeze metadata có thể tụt lại.

Không tắt autovacuum chỉ vì bảng không UPDATE/DELETE.

## 8. Các tham số threshold thường gặp

| Tham số | Vai trò |
| --- | --- |
| autovacuum_vacuum_threshold | Dead tuples tối thiểu trước khi xét vacuum |
| autovacuum_vacuum_scale_factor | Tỷ lệ theo kích thước bảng cho vacuum |
| autovacuum_vacuum_insert_threshold | Insert count cơ sở cho insert-triggered vacuum |
| autovacuum_vacuum_insert_scale_factor | Tỷ lệ theo kích thước bảng cho insert vacuum |
| autovacuum_analyze_threshold | Modification count cơ sở cho analyze |
| autovacuum_analyze_scale_factor | Tỷ lệ theo kích thước bảng cho analyze |
| autovacuum_vacuum_max_threshold | Giới hạn trên threshold vacuum nếu phiên bản hỗ trợ |

Một số tham số chỉ có trong các major version nhất định. Đừng đưa property mới vào config của server cũ mà không kiểm tra.

### Vì sao threshold tuyệt đối cũng quan trọng?

Với bảng lớn, chỉ giảm scale factor có thể khiến bảng nhỏ vacuum quá thường xuyên. Một base threshold cao hơn có thể giúp cân bằng.

Ví dụ:

~~~text
threshold = 2,000 + 0.01 * reltuples
~~~

Với 10 triệu rows, ngưỡng là 102.000 dead tuples. Với 10.000 rows, ngưỡng là 2.100. Cùng một cặp threshold/scale factor có tác động khác nhau theo kích thước relation.

## 9. Launcher cadence và số worker

Hai tham số quan trọng:

~~~conf
autovacuum_naptime = '1min'
autovacuum_max_workers = 3
~~~

Đây là các giá trị thường gặp ở nhiều cấu hình PostgreSQL, không phải lời khuyên phải dùng cho mọi server.

### autovacuum_naptime

Khoảng thời gian launcher chờ giữa các chu kỳ kiểm tra database. Launcher phân phối việc khởi động worker giữa các database trong cluster; không phải một timer bảo đảm từng bảng được vacuum đúng mỗi phút.

Nếu cluster có nhiều database và worker slots hạn chế, một bảng vừa đủ threshold có thể phải chờ worker rảnh.

### autovacuum_max_workers

Số autovacuum workers tối đa chạy đồng thời, không tính launcher.

Tăng số worker có thể giúp xử lý nhiều bảng/database cùng lúc, nhưng:

- Tăng concurrency CPU và I/O.
- Tăng memory usage tổng thể.
- Có thể cạnh tranh với workload ứng dụng.
- Tổng cost budget có cơ chế chia sẻ giữa các worker.
- Không tự tăng tốc một relation đơn lẻ theo tỷ lệ số worker.

### Khi nào tăng workers?

Cân nhắc khi:

- Nhiều bảng lớn cùng có backlog.
- Workers thường xuyên bận hết slots.
- CPU/I/O còn headroom.
- Transaction horizon không chặn cleanup.
- Memory budget đủ cho các worker đồng thời.

Nếu một bảng duy nhất vacuum chậm vì I/O hoặc old snapshots, chỉ tăng workers thường không giải quyết nguyên nhân.

## 10. Cost-based vacuum delay là gì?

VACUUM đọc page, kiểm tra tuple và cập nhật heap/index metadata. Hoạt động này tiêu thụ I/O và CPU. PostgreSQL có cơ chế **cost-based vacuum delay** để giới hạn tác động lên workload ứng dụng.

Thay vì chỉ đặt “chạy tối đa X MB/s”, PostgreSQL tính điểm chi phí cho một số thao tác page. Khi tích lũy cost đạt limit, worker nghỉ một khoảng thời gian theo cost delay.

### Các loại page cost

| Tham số | Ý nghĩa | Giá trị mặc định thường gặp |
| --- | --- | ---: |
| vacuum_cost_page_hit | Page đã ở shared buffer | 1 |
| vacuum_cost_page_miss | Cần đọc page từ storage | 2 |
| vacuum_cost_page_dirty | Page phải ghi thay đổi | 20 |

Các giá trị là cost units tương đối, không phải milliseconds hay bytes. Chúng giúp phân biệt thao tác có mức tác động khác nhau.

### Ví dụ khái niệm

Nếu worker đọc một page đã cache, cost tăng ít hơn so với việc đọc page từ storage hoặc làm dirty page. Khi tổng cost đạt giới hạn, worker ngủ theo delay để giảm áp lực I/O.

**Cost units không phải phép đo throughput thực tế.** Hai bảng có cùng cost limit vẫn có thể vacuum với tốc độ khác nhau do row width, index count, cache, storage latency và concurrent load.

## 11. vacuum_cost_limit và vacuum_cost_delay

Cấu hình thủ công VACUUM:

~~~conf
vacuum_cost_delay = 0
vacuum_cost_limit = 200
~~~

Cấu hình riêng cho autovacuum:

~~~conf
autovacuum_vacuum_cost_delay = '2ms'
autovacuum_vacuum_cost_limit = -1
~~~

Ý nghĩa:

- vacuum_cost_delay: delay của cost-based vacuum cho lệnh VACUUM thông thường.
- vacuum_cost_limit: cost limit của VACUUM thông thường.
- autovacuum_vacuum_cost_delay: delay riêng cho autovacuum worker.
- autovacuum_vacuum_cost_limit: cost limit riêng cho autovacuum; giá trị -1 thường có nghĩa dùng vacuum_cost_limit.

Không nhầm autovacuum_vacuum_cost_delay với autovacuum_naptime. Một tham số throttle bên trong công việc vacuum; tham số còn lại liên quan chu kỳ launcher.

### Tác động tuning

- Delay lớn hơn → worker ngủ nhiều hơn, thường giảm tác động I/O nhưng dọn chậm hơn.
- Delay nhỏ hơn → worker có thể hoạt động tích cực hơn, nhưng tăng contention.
- Cost limit lớn hơn → cần nhiều thao tác hơn mới chạm giới hạn, có thể tăng tốc và tăng áp lực.
- Cost limit nhỏ hơn → throttling sớm hơn, có thể giảm ảnh hưởng ứng dụng nhưng backlog tăng.

Không tăng cost limit khi storage đang ở saturation mà không đo; có thể làm workload chính tệ hơn.

## 12. Nhiều worker chia sẻ cost budget

Khi có nhiều autovacuum workers cùng chạy, PostgreSQL điều chỉnh/chia sẻ cost limit giữa các worker đang hoạt động để giới hạn tổng tác động theo cơ chế cost-based vacuum.

Hệ quả:

- Tăng autovacuum_max_workers không làm tổng I/O budget tăng tuyến tính.
- Mỗi worker có thể nhận phần cost budget nhỏ hơn khi nhiều worker cùng hoạt động.
- Nhiều relation có thể được xử lý song song, nhưng từng worker vẫn bị throttle.
- Tăng worker count mà không tăng tài nguyên I/O có thể làm latency ứng dụng tăng mà backlog không giảm đáng kể.

Vì vậy phải xem đồng thời autovacuum_max_workers, autovacuum_vacuum_cost_limit, autovacuum_vacuum_cost_delay và workload thực tế.

## 13. Anti-wraparound vacuum là trường hợp đặc biệt

Transaction ID PostgreSQL có không gian hữu hạn. Nếu database để các XID cũ tồn tại quá lâu mà không freeze, nguy cơ transaction ID wraparound có thể khiến dữ liệu cũ trở nên không an toàn về visibility.

Autovacuum thực hiện freeze để đánh dấu tuple đủ cũ theo quy tắc PostgreSQL là frozen, giúp tránh wraparound.

Các tham số liên quan:

- autovacuum_freeze_max_age
- vacuum_freeze_min_age
- vacuum_freeze_table_age
- vacuum_failsafe_age (tùy phiên bản)

### Anti-wraparound worker

Khi relation/database tiến gần ngưỡng freeze cần thiết, PostgreSQL có thể khởi chạy autovacuum worker đặc biệt để freeze tuples, kể cả khi autovacuum thường bị tắt.

Worker chống wraparound có mức ưu tiên bảo vệ tính đúng đắn của database. Cost-based delay có thể không được áp dụng như với worker vacuum thông thường được khởi chạy để dọn dead tuples; hãy đối chiếu tài liệu đúng version.

### Không tắt cơ chế freeze để giảm I/O

Nếu chống wraparound không theo kịp, PostgreSQL có thể tiến tới cảnh báo nghiêm trọng và từ chối một số thao tác ghi để bảo vệ database. Khi thấy cảnh báo XID age cao, cần xử lý ngay theo runbook DBA, không chỉ tăng threshold để trì hoãn vacuum.

## 14. Autovacuum work memory

Tham số:

~~~conf
autovacuum_work_mem = -1
~~~

-1 thường có nghĩa dùng maintenance_work_mem làm giá trị tương ứng cho worker. Nếu đặt một giá trị cụ thể, worker autovacuum dùng giới hạn đó theo cấu hình.

Memory có thể tăng theo số worker đồng thời. Ví dụ nếu mỗi worker có thể sử dụng một vùng memory đáng kể, ba worker cùng chạy có thể tiêu thụ nhiều hơn một worker đơn lẻ.

### Tuning cần cân bằng

- Số worker.
- autovacuum_work_mem.
- maintenance_work_mem.
- Index count và dead tuple volume.
- Memory dành cho workload query/sort/hash.
- Tổng RAM và các process khác trong host/container.

Không tăng autovacuum_work_mem lên rất lớn rồi nhân với autovacuum_max_workers mà không tính tổng memory budget.

## 15. Tuning theo từng bảng

Một global setting hiếm khi tối ưu cho mọi relation:

- Bảng nhỏ ít thay đổi.
- Bảng lớn UPDATE liên tục.
- Bảng log append-only.
- Bảng session có DELETE/expire thường xuyên.
- Bảng partition theo ngày/tháng.
- Bảng có nhiều index.

PostgreSQL cho phép storage parameters ở cấp table.

Ví dụ bảng lớn có churn cao:

~~~sql
ALTER TABLE public.orders
SET (
    autovacuum_vacuum_threshold = 1000,
    autovacuum_vacuum_scale_factor = 0.02,
    autovacuum_analyze_threshold = 500,
    autovacuum_analyze_scale_factor = 0.01
);
~~~

Ý nghĩa:

- Vacuum threshold gồm 1.000 dead tuples cộng 2% ước lượng row count.
- Analyze threshold gồm 500 modifications cộng 1% ước lượng row count.

Đây là **ví dụ minh họa**, không phải cấu hình production mặc định. Chọn con số từ workload và quan sát.

### Override cost per table

Một số phiên bản hỗ trợ storage parameters như:

~~~sql
ALTER TABLE public.orders
SET (
    autovacuum_vacuum_cost_delay = 1,
    autovacuum_vacuum_cost_limit = 1500
);
~~~

Đơn vị delay của table option được diễn giải theo tài liệu phiên bản; hãy kiểm tra pg_class.reloptions và docs. Không mặc định các tham số table-level có cùng phạm vi/context với GUC global.

### Reset về global defaults

~~~sql
ALTER TABLE public.orders
RESET (
    autovacuum_vacuum_threshold,
    autovacuum_vacuum_scale_factor,
    autovacuum_analyze_threshold,
    autovacuum_analyze_scale_factor,
    autovacuum_vacuum_cost_delay,
    autovacuum_vacuum_cost_limit
);
~~~

Chỉ reset các option thật sự đã được đặt và kiểm tra schema/table đúng trước khi thay đổi.

## 16. Ví dụ tính threshold cho bảng rất lớn

Giả sử một bảng có 200 triệu rows ước lượng:

- autovacuum_vacuum_threshold = 50
- autovacuum_vacuum_scale_factor = 0.20

Ngưỡng:

~~~text
50 + 0.20 * 200,000,000
= 40,000,050 dead tuples
~~~

Bảng có thể tích lũy hàng chục triệu dead tuples trước khi đạt ngưỡng theo công thức đó.

Nếu đặt scale factor 0.01 và threshold 5.000:

~~~text
5,000 + 0.01 * 200,000,000
= 2,005,000 dead tuples
~~~

Autovacuum được xét sớm hơn nhiều. Nhưng vacuum thường xuyên hơn cũng tạo I/O/CPU và index cleanup work.

**Không chọn scale factor nhỏ nhất có thể.** Chọn ngưỡng để tốc độ sinh dead tuples không vượt khả năng dọn dẹp mà vẫn giữ workload ổn định.

## 17. Bảng append-only và insert-triggered vacuum

Ví dụ bảng event:

~~~sql
CREATE TABLE public.event_log (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    occurred_at timestamptz NOT NULL,
    payload jsonb NOT NULL
);
~~~

Bảng chủ yếu INSERT. Nếu chỉ theo dõi dead tuples do UPDATE/DELETE, có thể ít khi đạt vacuum threshold. Insert-triggered vacuum hỗ trợ quản lý page mới và freezing.

Có thể đặt table options phù hợp workload:

~~~sql
ALTER TABLE public.event_log
SET (
    autovacuum_vacuum_insert_threshold = 5000,
    autovacuum_vacuum_insert_scale_factor = 0.05
);
~~~

Đây là ví dụ cho server có hỗ trợ insert-triggered vacuum parameters. Kiểm tra pg_settings trước khi dùng trên major version cũ.

### Append-only không có nghĩa không cần ANALYZE

Nếu phân bố occurred_at, event_type hoặc tenant IDs thay đổi, planner statistics vẫn cần được cập nhật. Insert volume lớn có thể làm query plan dựa trên thống kê cũ.

## 18. Bảng churn cao: UPDATE/DELETE liên tục

Một bảng session có thể liên tục hết hạn:

~~~sql
DELETE FROM public.sessions
WHERE expires_at < now();
~~~

Một job xóa hàng triệu rows trong transaction duy nhất có thể tạo lượng dead tuples lớn và transaction dài. Autovacuum không thể cleanup những tuple còn được snapshot cũ cần.

Hướng thiết kế:

- Xóa theo batch nhỏ, commit rõ ràng.
- Có index phù hợp trên expires_at.
- Tránh transaction xóa quá dài.
- Tune vacuum/analyze thresholds cho bảng.
- Theo dõi dead tuple backlog.
- Với retention theo thời gian, cân nhắc partition và DROP/DETACH partition thay vì DELETE từng hàng, nếu nghiệp vụ cho phép.

### DELETE batch minh họa

~~~sql
WITH batch AS (
    SELECT ctid
    FROM public.sessions
    WHERE expires_at < now()
    ORDER BY expires_at
    FOR UPDATE SKIP LOCKED
    LIMIT 5000
)
DELETE FROM public.sessions AS s
USING batch AS b
WHERE s.ctid = b.ctid;
~~~

ctid chỉ được dùng trong cùng statement để định vị các rows đã chọn. Nếu nhiều partitions, cần thêm tableoid. Đây là ví dụ bảo trì, không phải lời khuyên xóa dữ liệu mà chưa xác nhận retention policy.

## 19. Partitioning và autovacuum

Partitioning có thể giúp quản lý retention theo thời gian:

- Thay vì DELETE hàng chục triệu rows cũ, detach/drop partition đã hết hạn.
- Mỗi partition có thống kê và storage options riêng.
- Có thể tune autovacuum cho partition có churn khác nhau.

Nhưng:

- Partition con vẫn cần vacuum/analyze theo hoạt động của nó.
- Partitioned parent không chứa heap rows như table thường; autovacuum không vacuum parent như một heap relation.
- Sau thay đổi dữ liệu lớn ở partitions, có thể cần chạy ANALYZE thủ công trên parent để cập nhật thống kê phục vụ planning partitioned query, tùy phiên bản/hành vi.
- Thêm/drop partition là DDL và có lock/concurrency implications riêng.

Đừng nghĩ partitioning tự loại bỏ mọi nhu cầu VACUUM. Nó thay đổi cách dữ liệu được chia và retention được thực hiện.

## 20. Autovacuum có thể chạy nhưng không dọn được hết

Một nguyên nhân quan trọng: **old snapshots**.

VACUUM không thể loại bỏ một tuple version nếu một transaction còn có thể cần nhìn thấy nó theo MVCC visibility rules.

Các nguồn giữ cleanup horizon:

- Transaction chạy rất lâu.
- Session idle in transaction.
- Prepared transactions chưa kết thúc.
- Replication slots giữ xmin/catalog_xmin.
- Standby feedback (hot_standby_feedback) giữ row versions cần cho standby query.
- Một số replication/backup/decoding workflows.

### Hệ quả

Bạn có thể thấy autovacuum chạy, tiến trình đọc nhiều pages, nhưng n_dead_tup không giảm như mong đợi hoặc dead tuple cleanup bị hạn chế.

**Tăng cost limit không thể dọn một tuple mà snapshot cũ vẫn cần.** Phải tìm transaction/replication horizon giữ dữ liệu.

## 21. Kiểm tra transaction lâu

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    now() - xact_start AS transaction_age,
    backend_xmin,
    wait_event_type,
    wait_event,
    left(query, 200) AS query_sample
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
~~~

Tìm:

- Transaction mở lâu.
- idle in transaction.
- Backend có backend_xmin cũ.
- Query hoặc app giữ transaction qua thời gian dài.

Cột query có thể chứa SQL literals nhạy cảm; chỉ cấp quyền xem cho người cần. Nếu không cần query text, bỏ cột đó khỏi dashboard.

## 22. Kiểm tra replication slots

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    xmin,
    catalog_xmin,
    restart_lsn
FROM pg_replication_slots
ORDER BY slot_name;
~~~

Một replication slot không được consumer tiến lên có thể giữ WAL và/hoặc xmin horizon, gây:

- WAL retention tăng.
- Disk đầy.
- Vacuum cleanup bị giữ lại trong một số trường hợp.
- Catalog bloat nếu catalog_xmin cũ.

Không xóa replication slot chỉ để “VACUUM chạy nhanh”. Trước tiên xác định consumer, khả năng resume và hậu quả replication/data loss.

## 23. Kiểm tra prepared transactions

~~~sql
SELECT
    transaction,
    gid,
    prepared,
    owner,
    database
FROM pg_prepared_xacts
ORDER BY prepared;
~~~

Prepared transaction có thể tồn tại lâu nếu ứng dụng 2PC hoặc coordinator gặp lỗi. Nó có thể giữ transaction state và ảnh hưởng cleanup.

Không tự ROLLBACK PREPARED một transaction chưa xác định; cần phối hợp với transaction coordinator và quy trình recovery.

## 24. Kiểm tra thống kê bảng

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    n_mod_since_analyze,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count,
    last_analyze,
    last_autoanalyze,
    autoanalyze_count
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 30;
~~~

Ý nghĩa:

- n_live_tup: ước lượng số live tuples.
- n_dead_tup: ước lượng số dead tuples.
- n_mod_since_analyze: số modifications ước lượng từ lần analyze gần nhất.
- last_autovacuum: lần autovacuum gần nhất.
- autovacuum_count: số lần autovacuum được thống kê.
- last_autoanalyze: lần autoanalyze gần nhất.

### Các số liệu là ước lượng

n_live_tup/n_dead_tup không phải COUNT(*) chính xác. Statistics có thể trễ hoặc được reset. Hãy xem xu hướng qua thời gian và kết hợp progress/logs, không đưa ra kết luận từ một snapshot đơn.

Một số cột statistics có thể khác giữa major versions. Nếu query gặp lỗi do cột không tồn tại trên server cũ, tra catalog của version đó và điều chỉnh.

## 25. Xem tiến độ VACUUM hiện tại

PostgreSQL có pg_stat_progress_vacuum:

~~~sql
SELECT
    pid,
    datname,
    relid::regclass AS relation_name,
    phase,
    heap_blks_total,
    heap_blks_scanned,
    heap_blks_vacuumed,
    index_vacuum_count,
    num_dead_tuples,
    max_dead_tuples
FROM pg_stat_progress_vacuum
ORDER BY datname, relation_name;
~~~

Các phase có thể bao gồm:

- Initializing.
- Scanning heap.
- Vacuuming indexes.
- Vacuuming heap.
- Cleaning up indexes.
- Truncating heap.
- Performing final cleanup.

Các cột progress cho biết worker đang ở giai đoạn nào và đã xử lý bao nhiêu block theo cách PostgreSQL báo cáo.

### Không suy phần trăm hoàn thành chỉ từ một cột

heap_blks_scanned / heap_blks_total không phải lúc nào cũng là phần trăm tổng công việc còn lại, vì index cleanup, heap vacuum, truncation và final cleanup có chi phí riêng. Hãy xem phase cùng các counter.

## 26. Xem autovacuum worker trong pg_stat_activity

~~~sql
SELECT
    pid,
    backend_type,
    datname,
    usename,
    application_name,
    state,
    query_start,
    wait_event_type,
    wait_event,
    left(query, 200) AS query_sample
FROM pg_stat_activity
WHERE backend_type = 'autovacuum worker'
ORDER BY query_start;
~~~

backend_type và chi tiết session có thể phụ thuộc version/quyền xem. Trong một số phiên bản/cấu hình, có thể lọc theo query/application metadata khác.

Không nhầm worker với launcher; launcher là tiến trình điều phối, worker thực hiện công việc relation.

## 27. Đọc cấu hình đang hiệu lực

~~~sql
SELECT
    name,
    setting,
    unit,
    context,
    source,
    pending_restart
FROM pg_settings
WHERE name IN (
    'autovacuum',
    'track_counts',
    'autovacuum_naptime',
    'autovacuum_max_workers',
    'autovacuum_vacuum_threshold',
    'autovacuum_vacuum_scale_factor',
    'autovacuum_vacuum_insert_threshold',
    'autovacuum_vacuum_insert_scale_factor',
    'autovacuum_analyze_threshold',
    'autovacuum_analyze_scale_factor',
    'autovacuum_vacuum_cost_delay',
    'autovacuum_vacuum_cost_limit',
    'autovacuum_work_mem',
    'autovacuum_freeze_max_age'
)
ORDER BY name;
~~~

Các trường:

- setting: giá trị hiệu lực.
- unit: đơn vị.
- context: phạm vi thay đổi (postmaster, sighup, superuser, user...).
- source: nguồn cấu hình.
- pending_restart: có cần restart để áp dụng hay không.

Không giả định mọi tham số autovacuum có thể đổi bằng reload. Một số cấu hình cần restart, tùy context.

## 28. Xem reloptions theo từng bảng

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    c.reloptions
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'm')
  AND c.reloptions IS NOT NULL
ORDER BY n.nspname, c.relname;
~~~

reloptions cho biết storage parameters đã override trên relation. Một bảng có thể có vacuum scale factor rất khác global GUC.

Nếu tuning mà chỉ xem pg_settings, bạn có thể bỏ qua table-level overrides.

## 29. Bật log để hiểu autovacuum làm gì

PostgreSQL có tham số:

~~~conf
log_autovacuum_min_duration = '1s'
~~~

Nó có thể log các autovacuum/autoanalyze operations đáp ứng ngưỡng thời gian đã cấu hình. Giá trị chính xác và cách diễn giải cần xem docs version.

Một số lựa chọn:

- -1: tắt logging theo tham số này.
- 0: log mọi autovacuum operation theo semantics tham số.
- Giá trị dương: log operation mất ít nhất thời lượng đó.

### Lợi ích

Log có thể giúp nhận diện:

- Relation được vacuum.
- Số pages/tuples được xử lý.
- Index cleanup.
- Worker bị cancel hoặc gặp điều kiện đặc biệt.
- Công việc kéo dài và nguyên nhân có thể quan sát.

### Rủi ro

Log mọi worker trên cluster lớn có thể tạo volume cao. Bảo vệ log, đặt retention và không ghi nội dung nhạy cảm không cần thiết.

## 30. Chẩn đoán: bảng có nhiều dead tuples nhưng autovacuum chưa chạy

Kiểm tra theo thứ tự:

1. autovacuum có bật không?
2. track_counts có bật không?
3. pg_stat_user_tables.n_dead_tup có vượt threshold ước lượng không?
4. Table-level reloptions có override threshold không?
5. autovacuum_max_workers có hết slot không?
6. Launcher có chạy và database có được kiểm tra không?
7. Worker có bị block/cancel bởi DDL hoặc lock conflict không?
8. Logs có ghi lỗi hoặc cancellation không?
9. Table có temporary/unlogged/special relation behavior cần xem riêng không?
10. Có transaction horizon ngăn cleanup dù worker vẫn chạy không?

### Tính threshold thực tế gần đúng

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    current_setting('autovacuum_vacuum_threshold')::numeric
      + current_setting('autovacuum_vacuum_scale_factor')::numeric
        * GREATEST(reltuples, 0) AS estimated_global_threshold
FROM pg_stat_user_tables AS s
JOIN pg_class AS c
    ON c.oid = s.relid
ORDER BY n_dead_tup DESC;
~~~

Câu query minh họa global settings và reltuples; nó **không tính table-level reloptions**, insert threshold, version-specific max threshold, stats lag hoặc mọi điều kiện scheduling. Dùng để định hướng, không phải mô phỏng chính xác quyết định nội bộ của launcher.

## 31. Chẩn đoán: autovacuum chạy nhưng tốc độ thấp

Các nguyên nhân có thể:

- Cost delay lớn.
- Cost limit thấp.
- Nhiều workers chia sẻ budget.
- Storage latency cao.
- CPU/IO đang bị workload khác sử dụng.
- Nhiều index cần cleanup.
- Row width/TOAST lớn.
- Dead tuple count cao.
- Snapshot cũ giữ cleanup horizon.
- Relation lớn hoặc có nhiều page cần scan.
- Worker bị gián đoạn bởi lock conflict/DDL.

### Không chỉ tăng autovacuum_vacuum_cost_limit

Nếu nguyên nhân là long-running transaction hoặc replication slot, tăng cost limit không làm tuple trở nên removable.

Nếu nguyên nhân là storage saturation, tăng cost limit có thể làm latency query tăng thêm.

Trước khi tuning, đọc progress phase, server logs, wait events, transaction age và replication state.

## 32. Chẩn đoán: autovacuum chạy quá thường xuyên

Một số bảng nhỏ hoặc write-heavy có thể được vacuum/analyze liên tục nếu threshold quá thấp.

Tác động:

- Tăng I/O/WAL.
- Tăng CPU và contention.
- Tạo nhiều autovacuum log.
- Tăng số lần analyze và planning stats updates.
- Có thể làm workload chính dao động.

Cách tiếp cận:

- Kiểm tra table size và modification rate.
- Tách vacuum threshold và analyze threshold.
- Xem table-level reloptions.
- Không nâng threshold toàn cluster nếu chỉ một bảng có vấn đề.
- Xem xét partitioning/retention.
- Đo độ mới của planner stats trước khi nới analyze threshold.

## 33. Chẩn đoán: bảng phình dù autovacuum chạy

Autovacuum không phải công cụ tự động thu nhỏ file về filesystem.

Các trường hợp:

- Dead tuples được chuyển thành free space có thể tái sử dụng nhưng file vẫn giữ kích thước.
- Một số page ở cuối relation có thể được truncate nếu điều kiện/lock cho phép, nhưng không phải lúc nào cũng làm được.
- Long-running snapshots ngăn cleanup.
- Index bloat có thể cần điều tra riêng.
- Workload churn cao liên tục tạo dead tuples mới.
- Table fillfactor/index design khiến page layout không phù hợp.

### Không dùng VACUUM FULL như phản xạ đầu tiên

VACUUM FULL rewrite relation, cần lock mạnh và thêm disk space trong quá trình thực hiện. Cần maintenance window, dung lượng, lock plan và đánh giá impact.

Các phương án khác tùy trường hợp có thể gồm partition retention, pg_repack (extension/tool ngoài core), index rebuild phù hợp hoặc điều chỉnh schema/workload. Chọn theo bằng chứng, không dựa vào kích thước file đơn lẻ.

## 34. Cost limit và độ trễ ứng dụng

~~~text
Cost delay cao / cost limit thấp
    -> ít I/O pressure hơn
    -> worker có thể chạy lâu hơn
    -> dead tuple backlog có thể tăng

Cost delay thấp / cost limit cao
    -> worker tích cực hơn
    -> cleanup có thể nhanh hơn
    -> CPU/I/O contention có thể tăng
    -> query latency có thể xấu đi
~~~

Cần đặt SLO cho cả hai phía:

- Query/API p95/p99.
- Vacuum backlog/oldest dead tuples.
- Transaction ID age.
- Replication lag.
- Disk growth.
- Autovacuum worker utilization.

Không tối ưu vacuum throughput nếu làm database phục vụ ứng dụng chậm hơn mức chấp nhận.

## 35. autovacuum_max_workers và naptime không thay threshold

Các tham số điều khiển những phần khác nhau:

| Nhóm | Tham số | Câu hỏi trả lời |
| --- | --- | --- |
| Eligibility | Threshold/scale factor | Khi nào bảng đủ điều kiện? |
| Scheduling | autovacuum_naptime | Launcher kiểm tra/điều phối theo chu kỳ nào? |
| Concurrency | autovacuum_max_workers | Bao nhiêu worker chạy cùng lúc? |
| Throttling | Cost delay/limit | Worker tác động I/O ở mức nào? |
| Memory | autovacuum_work_mem | Worker có bao nhiêu memory cho vacuum work? |
| Safety | Freeze ages | Khi nào cần freeze chống wraparound? |

Nếu bảng chỉ đạt threshold sau nhiều giờ, giảm naptime không làm threshold biến mất. Nếu tất cả worker slots bận, tăng cost limit cũng không tạo worker mới.

## 36. Anti-wraparound và kiểm tra XID age

Kiểm tra database age:

~~~sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age
FROM pg_database
ORDER BY xid_age DESC;
~~~

Kiểm tra relation:

~~~sql
SELECT
    n.nspname,
    c.relname,
    age(c.relfrozenxid) AS xid_age
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'm')
ORDER BY xid_age DESC
LIMIT 30;
~~~

Các con số cần được so với freeze settings của server. Không dùng một ngưỡng cố định từ bài viết để kết luận mức an toàn cho mọi version.

### Khi XID age cao

- Kiểm tra autovacuum logs.
- Kiểm tra worker slots và I/O.
- Tìm long-running transaction/prepared transaction.
- Kiểm tra replication slots và standby feedback.
- Xác định relation lớn nhất/oldest relfrozenxid.
- Lập kế hoạch vacuum/freeze có kiểm soát.
- Theo dõi cảnh báo wraparound và failsafe.

Đừng chỉ tăng autovacuum_freeze_max_age để trì hoãn cảnh báo; điều đó có thể tăng lượng dữ liệu cần xử lý và rủi ro.

## 37. Freeze không phải xóa dữ liệu

VACUUM freeze không xóa row. Nó giúp đánh dấu transaction IDs đủ cũ để PostgreSQL có thể tiếp tục diễn giải visibility an toàn khi XID counter quay vòng.

Phân biệt:

- Dead tuple cleanup: loại bỏ tuple version không còn cần.
- Freeze: đánh dấu XID metadata đủ cũ.
- Analyze: cập nhật thống kê planner.
- Full rewrite: tạo physical relation mới/compact.

Một vacuum có thể làm nhiều việc trong một lượt, nhưng mục tiêu và trigger conditions khác nhau.

## 38. Autovacuum và index cleanup

VACUUM xử lý dead tuple references trong indexes theo quy trình phù hợp. Số lượng và kích thước indexes ảnh hưởng đáng kể thời gian vacuum.

Một table có 15 indexes có thể tốn nhiều công cleanup hơn table có 2 indexes cùng số rows.

### Vì sao không drop index để vacuum nhanh?

Index có thể phục vụ query, UNIQUE constraints, foreign keys và workload khác. Chỉ xóa index sau khi chứng minh không cần và có migration plan.

Các option như INDEX_CLEANUP/PROCESS_MAIN có semantics version-specific; không tắt index cleanup toàn cục chỉ để một vacuum chạy nhanh nếu chưa đánh giá index bloat và correctness.

## 39. Visibility map và index-only scan

VACUUM cập nhật visibility map để PostgreSQL biết page nào chứa tuples đã visible với mọi transaction cần xét theo điều kiện thích hợp.

Khi visibility map đánh dấu all-visible, một số Index Only Scan có thể tránh heap fetch cho page tương ứng.

Nếu insert/update liên tục, visibility map bits có thể bị clear và cần vacuum để thiết lập lại sau khi đủ điều kiện.

Kiểm tra query plan:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id
FROM public.orders
WHERE order_id BETWEEN 1000 AND 2000;
~~~

Xem Heap Fetches nếu plan là Index Only Scan. Autovacuum không đảm bảo mọi query thành index-only; index coverage, visibility map và planner choice vẫn quan trọng.

## 40. Autovacuum trên bảng có TOAST

Các bảng có giá trị text/JSON/binary lớn có thể dùng TOAST relation. Storage parameters và vacuum work liên quan đến TOAST có thể ảnh hưởng cleanup.

Khi điều tra table lớn:

- Xem pg_total_relation_size() và pg_relation_size().
- Kiểm tra index size.
- Nhớ rằng TOAST relation có thể chiếm phần lớn tổng dung lượng.
- Một số table storage parameters có biến thể toast. theo cú pháp hỗ trợ; chỉ dùng khi hiểu đúng relation và version.

Không chỉ nhìn heap size rồi kết luận vacuum đã xử lý hết dung lượng của bảng.

## 41. Bulk load và ANALYZE

Sau khi nạp hàng triệu rows bằng COPY hoặc bulk INSERT:

- Planner statistics có thể chưa phản ánh phân bố mới.
- Autovacuum/autoanalyze có thể chưa chạy ngay.
- Query production ngay sau import có thể chọn plan không tối ưu.

Có thể chủ động:

~~~sql
ANALYZE public.orders;
~~~

Nếu bulk load đồng thời tạo dead tuples hoặc cần freeze/visibility maintenance, đánh giá VACUUM riêng. Không phải mọi lần INSERT lớn đều cần VACUUM ngay; ANALYZE và VACUUM phục vụ mục tiêu khác nhau.

## 42. Partitioned table và ANALYZE parent

Autovacuum vacuum các partition con theo dữ liệu vật lý của chúng. Parent partitioned table không có heap rows như một table thường. Vì vậy, sau thay đổi lớn ở partitions, hãy xem thống kê ở parent có được cập nhật theo nhu cầu planner hay không.

Có thể chạy thủ công:

~~~sql
ANALYZE public.partitioned_orders;
~~~

Điều này đặc biệt hữu ích khi phân bố dữ liệu hoặc số lượng rows ở các partitions thay đổi đáng kể. Hãy xác nhận hành vi autoanalyze theo major version đang dùng.

## 43. Chẩn đoán worker bị block hoặc bị hủy

Autovacuum có thể bị ảnh hưởng bởi DDL/lock conflicts. Kiểm tra:

~~~sql
SELECT
    a.pid,
    a.backend_type,
    a.datname,
    a.query_start,
    a.wait_event_type,
    a.wait_event,
    l.locktype,
    l.mode,
    l.granted,
    l.relation::regclass AS relation_name
FROM pg_stat_activity AS a
LEFT JOIN pg_locks AS l
    ON l.pid = a.pid
WHERE a.backend_type = 'autovacuum worker'
ORDER BY a.query_start;
~~~

Nếu worker không có lock phù hợp hoặc bị cancel, xem log server và hoạt động DDL cùng thời điểm.

Không kết luận một worker bị block chỉ vì query progress đứng yên trong vài giây; một phase có thể làm việc nặng mà counter không tăng đều.

## 44. Cấu hình tham khảo cho workload khác nhau

Các mẫu dưới đây chỉ là điểm bắt đầu để benchmark, không phải profile production sẵn dùng.

### Bảng nhỏ, ít thay đổi

Giữ global defaults thường hợp lý. Đừng giảm threshold quá thấp khiến bảng nhỏ vacuum/analyze liên tục.

### Bảng lớn, UPDATE/DELETE nhiều

Có thể thử:

~~~sql
ALTER TABLE public.orders
SET (
    autovacuum_vacuum_threshold = 2000,
    autovacuum_vacuum_scale_factor = 0.01,
    autovacuum_analyze_threshold = 1000,
    autovacuum_analyze_scale_factor = 0.02
);
~~~

Theo dõi n_dead_tup, query latency, worker runtime và I/O trước/sau.

### Bảng append-only

Cân nhắc insert-triggered vacuum:

~~~sql
ALTER TABLE public.event_log
SET (
    autovacuum_vacuum_insert_threshold = 5000,
    autovacuum_vacuum_insert_scale_factor = 0.05
);
~~~

Theo dõi visibility map, index-only scan, insert rate và XID age.

### Bảng retention theo partition

Cân nhắc drop/detach partition theo retention policy. Không xóa hàng triệu rows chỉ để autovacuum dọn sau đó nếu partition lifecycle cho phép DDL an toàn.

## 45. Một quy trình tuning có kiểm soát

1. Chụp baseline: relation sizes, n_live_tup/n_dead_tup, autovacuum count, worker progress, XID age.
2. Xác định bảng gây backlog và tốc độ phát sinh dead tuples.
3. Xác định nguyên nhân: threshold, worker slots, cost throttle, I/O, lock hoặc old snapshot.
4. Chỉ thay một nhóm tham số có liên quan.
5. Dùng table-level reloptions nếu vấn đề chỉ ở vài bảng.
6. Đo query p95/p99, autovacuum runtime, disk/WAL và replication lag.
7. Quan sát qua nhiều chu kỳ, không kết luận từ một lần vacuum.
8. Kiểm tra freeze age và đảm bảo chống wraparound.
9. Ghi lại giá trị cũ, giá trị mới, lý do và rollback plan.
10. Xem lại tuning khi workload hoặc kích thước bảng thay đổi.

### Tránh tuning phản ứng

- Backlog tăng → tăng worker ngay.
- Query chậm → tắt autovacuum.
- File lớn → chạy VACUUM FULL.
- Worker ngủ → cost delay về 0.

Mỗi hành động có thể làm vấn đề tệ hơn nếu nguyên nhân thật là snapshot cũ, disk saturation, threshold sai hoặc index bloat.

## 46. Các sai lầm thường gặp

1. **Tắt autovacuum toàn cluster** để giảm I/O, rồi tích lũy dead tuples và XID age.
2. **Tắt track_counts** nhưng vẫn kỳ vọng autovacuum ra quyết định đúng.
3. **Nghĩ autovacuum_naptime là lịch vacuum cố định cho từng bảng**.
4. **Tăng autovacuum_max_workers mà không tính CPU/I/O/memory**.
5. **Cho rằng nhiều worker làm một bảng vacuum nhanh tuyến tính**.
6. **Nhầm cost units với MB/s hoặc milliseconds**.
7. **Đặt cost limit rất cao khi storage đã saturation**.
8. **Đặt cost delay quá cao khiến backlog tăng**.
9. **Chỉ tune global threshold cho một bảng lớn**, làm mọi bảng khác bị ảnh hưởng.
10. **Không tính threshold theo reltuples**, dẫn tới bảng 100 triệu rows chờ quá nhiều dead tuples.
11. **Chỉ theo dõi dead tuples, bỏ qua analyze statistics**.
12. **Nghĩ append-only không cần vacuum**, bỏ qua insert-triggered vacuum/freeze/visibility map.
13. **Tăng autovacuum_work_mem mà không nhân với số worker**.
14. **Không xem reloptions**, tưởng global GUC đang áp dụng cho bảng.
15. **Nhầm VACUUM thường với VACUUM FULL**.
16. **Kỳ vọng VACUUM thường trả hết file size về OS**.
17. **Chạy VACUUM FULL trên bảng lớn mà không tính lock và disk headroom**.
18. **Tăng cost limit để giải quyết old snapshot**, dù tuple chưa thể cleanup.
19. **Bỏ qua idle-in-transaction và prepared transactions**.
20. **Không kiểm tra replication slot/standby feedback** khi xmin horizon bị giữ.
21. **Chỉ xem pg_stat_user_tables một lần**, không theo dõi xu hướng.
22. **Diễn giải progress vacuum như phần trăm hoàn thành toàn bộ công việc**.
23. **Tắt anti-wraparound/autovacuum freeze** vì muốn tránh worker chạy.
24. **Tăng autovacuum_freeze_max_age để trì hoãn cảnh báo** mà không có kế hoạch.
25. **Không analyze parent partitioned table sau thay đổi lớn ở partitions**.
26. **Cho rằng index cleanup không đáng kể**, dù table có nhiều indexes.
27. **Chỉ nhìn heap size, bỏ qua TOAST và indexes**.
28. **Chạy ANALYZE rồi nghĩ đã thay VACUUM**.
29. **Chạy VACUUM rồi nghĩ planner statistics chắc chắn mới**.
30. **Không đo impact trên query latency/replication lag** sau tuning.

## 47. Bài tập thực hành có đáp án

### Bài 1. Autovacuum gồm những thành phần chính nào?

**Đáp án:** Launcher điều phối và khởi chạy worker; worker thực hiện vacuum/analyze trên relation đủ điều kiện.

### Bài 2. track_counts có vai trò gì?

**Đáp án:** Thu thập thống kê hoạt động bảng cần cho quyết định autovacuum. Phải bật để autovacuum hoạt động đúng.

### Bài 3. VACUUM khác ANALYZE thế nào?

**Đáp án:** VACUUM xử lý dead tuples, visibility/freeze; ANALYZE cập nhật thống kê planner.

### Bài 4. Tính vacuum threshold

Giả sử threshold = 50, scale factor = 0.2, reltuples = 1.000.000.

**Đáp án:** 50 + 0.2 × 1.000.000 = 200.050 dead tuples.

### Bài 5. Vì sao scale factor 0.2 quá lớn với bảng 500 triệu rows?

**Đáp án:** Ngưỡng tỷ lệ có thể lên tới khoảng 100 triệu dead tuples, để bảng tích lũy nhiều dead space trước khi đủ điều kiện vacuum.

### Bài 6. Analyze threshold dựa trên gì?

**Đáp án:** Base threshold cộng scale factor nhân với số rows ước lượng; trigger dựa trên modifications kể từ lần analyze gần nhất.

### Bài 7. Insert-only table có cần vacuum không?

**Đáp án:** Có thể cần insert-triggered vacuum để xử lý page mới, visibility map và freezing.

### Bài 8. autovacuum_naptime có nghĩa gì?

**Đáp án:** Khoảng chu kỳ launcher kiểm tra/điều phối database; không bảo đảm từng table vacuum đúng sau thời gian đó.

### Bài 9. autovacuum_max_workers là gì?

**Đáp án:** Giới hạn số autovacuum worker đồng thời trong cluster.

### Bài 10. Tăng workers có làm một bảng vacuum nhanh gấp đôi?

**Đáp án:** Không. Worker count chủ yếu tăng concurrency giữa công việc; cost budget được chia sẻ và một worker không tự chia một relation vacuum thành nhiều tiến trình.

### Bài 11. Cost page hit/miss/dirty là gì?

**Đáp án:** Cost units tương đối cho page đã cache, phải đọc từ storage và page bị dirty; không phải bytes hoặc thời gian trực tiếp.

### Bài 12. autovacuum_vacuum_cost_limit = -1 nghĩa gì?

**Đáp án:** Theo cấu hình phổ biến, dùng giá trị vacuum_cost_limit làm cost limit cho autovacuum; xác nhận bằng tài liệu version và pg_settings.

### Bài 13. Tăng cost limit có rủi ro gì?

**Đáp án:** Worker có thể chạy tích cực hơn, tăng CPU/I/O contention và query latency.

### Bài 14. Vì sao cost delay không giải quyết old snapshots?

**Đáp án:** Snapshot cũ khiến tuple chưa thể loại bỏ; thay đổi tốc độ worker không làm tuple trở nên removable.

### Bài 15. autovacuum_work_mem = -1 nghĩa gì?

**Đáp án:** Dùng maintenance_work_mem làm giá trị tương ứng theo cấu hình PostgreSQL.

### Bài 16. Vì sao memory phải tính theo worker count?

**Đáp án:** Nhiều worker có thể dùng memory đồng thời, nên tổng budget có thể tăng theo concurrency.

### Bài 17. Table-level reloptions dùng để làm gì?

**Đáp án:** Override threshold/cost/autovacuum behavior cho một relation mà không cần thay global settings.

### Bài 18. Tắt autovacuum trên một table có tắt anti-wraparound?

**Đáp án:** Không nên giả định như vậy. PostgreSQL vẫn có thể chạy worker chống wraparound; nhưng tắt autovacuum thường làm mất maintenance thông thường.

### Bài 19. Anti-wraparound vacuum giải quyết gì?

**Đáp án:** Freeze tuple transaction IDs để ngăn XID wraparound đe dọa tính đúng đắn database.

### Bài 20. Xem database XID age

~~~sql
SELECT datname, age(datfrozenxid) AS xid_age
FROM pg_database
ORDER BY xid_age DESC;
~~~

**Đáp án:** Cho biết tuổi transaction ID theo database để xác định nơi cần theo dõi freeze.

### Bài 21. pg_stat_user_tables có n_dead_tup chính xác tuyệt đối không?

**Đáp án:** Không. Đây là thống kê ước lượng, cần xem xu hướng và kết hợp các nguồn khác.

### Bài 22. Xem progress vacuum bằng view nào?

**Đáp án:** pg_stat_progress_vacuum.

### Bài 23. Một transaction idle in transaction có thể gây gì?

**Đáp án:** Giữ snapshot/xmin horizon, khiến VACUUM không thể cleanup một số tuple versions.

### Bài 24. Replication slot có thể ảnh hưởng vacuum không?

**Đáp án:** Có. xmin/catalog_xmin của slot có thể giữ cleanup horizon; slot lag còn có thể giữ WAL.

### Bài 25. VACUUM thường có trả file size về OS không?

**Đáp án:** Thường chủ yếu làm space tái sử dụng trong relation; chỉ một số điều kiện truncation có thể trả phần cuối file. VACUUM FULL mới rewrite/compact.

### Bài 26. Vì sao bảng có nhiều index vacuum lâu?

**Đáp án:** Cleanup dead index entries và index maintenance tạo thêm công việc.

### Bài 27. Tại sao bảng partitioned cần ANALYZE parent?

**Đáp án:** Parent không có heap rows như bảng thường; sau thay đổi lớn ở partitions, thống kê parent có thể cần cập nhật để planner ước lượng đúng.

### Bài 28. Chạy ANALYZE có thay VACUUM không?

**Đáp án:** Không. ANALYZE cập nhật thống kê, không thay việc dọn dead tuples/freeze.

### Bài 29. Tuning cho bảng 200 triệu rows, scale 0.01 và threshold 5000?

**Đáp án:** Ngưỡng ước lượng là 5.000 + 2.000.000 = 2.005.000 dead tuples.

### Bài 30. Autovacuum đang chạy nhưng n_dead_tup không giảm; kiểm tra gì trước?

**Đáp án:** Kiểm tra transaction lâu, backend_xmin, prepared transactions, replication slots/standby feedback, worker phase và lock/logs trước khi tăng cost limit.

## 48. Checklist vận hành

- [ ] autovacuum bật và track_counts bật.
- [ ] Hiểu launcher/worker và worker slots.
- [ ] Xem threshold/scale factor global và table-level.
- [ ] Tính threshold cho bảng lớn bằng reltuples ước lượng.
- [ ] Theo dõi vacuum và analyze riêng.
- [ ] Xem insert-triggered vacuum cho bảng append-only.
- [ ] Tuning autovacuum_naptime theo số database và workload.
- [ ] Không tăng autovacuum_max_workers mà không tính CPU/I/O/memory.
- [ ] Hiểu cost units, cost delay và cost limit.
- [ ] Kiểm tra cost budget được chia sẻ giữa workers.
- [ ] Tính tổng memory của autovacuum workers.
- [ ] Dùng reloptions cho bảng đặc biệt thay vì đổi global tùy tiện.
- [ ] Theo dõi anti-wraparound và age(datfrozenxid).
- [ ] Không tắt freeze/autovacuum để né I/O.
- [ ] Kiểm tra long-running transaction và idle-in-transaction.
- [ ] Kiểm tra prepared transactions.
- [ ] Kiểm tra replication slots và standby feedback.
- [ ] Theo dõi n_dead_tup, last_autovacuum, autovacuum_count.
- [ ] Theo dõi pg_stat_progress_vacuum và worker wait events.
- [ ] Bật log autovacuum có ngưỡng phù hợp.
- [ ] Phân biệt VACUUM thường và VACUUM FULL.
- [ ] Không kỳ vọng VACUUM thường thu nhỏ relation về filesystem.
- [ ] Theo dõi index/TOAST size, không chỉ heap.
- [ ] Chạy ANALYZE parent sau thay đổi partition đáng kể khi cần.
- [ ] Benchmark trước/sau với query p95/p99, IO, WAL và replication lag.
- [ ] Có runbook khi XID age tiến gần ngưỡng cảnh báo.

## 49. Tài liệu PostgreSQL chính thức

Đọc theo major version đang triển khai:

- [Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html) — VACUUM, autovacuum, dead tuples, freeze và statistics.
- [Autovacuum Configuration](https://www.postgresql.org/docs/current/runtime-config-autovacuum.html) — launcher, worker, thresholds, cost delay, memory và freeze settings.
- [Resource Consumption](https://www.postgresql.org/docs/current/runtime-config-resource.html) — cost-based vacuum delay và memory settings.
- [VACUUM](https://www.postgresql.org/docs/current/sql-vacuum.html) — options, VERBOSE, ANALYZE, FULL và freeze.
- [ANALYZE](https://www.postgresql.org/docs/current/sql-analyze.html) — cập nhật planner statistics.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — pg_stat_user_tables, pg_stat_activity và progress views.
- [Progress Reporting](https://www.postgresql.org/docs/current/progress-reporting.html) — pg_stat_progress_vacuum.
- [System Catalog pg_class](https://www.postgresql.org/docs/current/catalog-pg-class.html) — reltuples, reloptions và relfrozenxid.
- [System Catalog pg_database](https://www.postgresql.org/docs/current/catalog-pg-database.html) — datfrozenxid.
- [Replication Slots](https://www.postgresql.org/docs/current/view-pg-replication-slots.html) — xmin/catalog_xmin và slot state.
- [Hot Standby](https://www.postgresql.org/docs/current/hot-standby.html) — feedback và conflict behavior.
- [Transaction ID Wraparound](https://www.postgresql.org/docs/current/routine-vacuuming.html#VACUUM-FOR-WRAPAROUND) — freeze và wraparound prevention.
- [Table Partitioning](https://www.postgresql.org/docs/current/ddl-partitioning.html) — partition maintenance và statistics.
- [ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html) — storage parameters của relation.

Các URL /current/ trỏ tới tài liệu PostgreSQL hiện hành. Thresholds, progress columns, insert-triggered vacuum và một số cost/freeze parameters có thể thay đổi giữa major versions; kiểm tra pg_settings và tài liệu đúng version trước khi triển khai.

## 50. Tổng kết

**Autovacuum là một hệ thống điều phối và bảo trì nền có ngưỡng kích hoạt, giới hạn concurrency, cost throttling và yêu cầu bảo vệ transaction ID.** Muốn nó theo kịp workload phải xử lý đúng nguyên nhân, không chỉ tăng một tham số.

1. **Launcher điều phối, worker thực thi.** autovacuum_max_workers giới hạn số worker đồng thời, không chia một lần vacuum của một bảng thành nhiều tiến trình tự động.
2. **Threshold quyết định khi nào relation đủ điều kiện.** Scale factor 20% có thể quá cao cho bảng hàng trăm triệu rows.
3. **VACUUM, ANALYZE và insert-triggered vacuum có mục tiêu riêng.** Bảng append-only vẫn có thể cần vacuum.
4. **Cost delay/limit điều tiết tác động I/O.** Cost units là điểm tương đối, không phải MB/s.
5. **Nhiều worker chia sẻ cost budget.** Tăng concurrency không đồng nghĩa tổng throughput tăng tuyến tính.
6. **Table-level reloptions giúp tune riêng bảng lớn/churn cao** mà không làm mọi relation thay đổi theo.
7. **Autovacuum work memory nhân theo worker concurrency**, cần tính tổng RAM.
8. **Anti-wraparound vacuum là cơ chế bảo vệ bắt buộc về mặt vận hành.** Không tắt freeze để giảm tải.
9. **Long-running snapshots, prepared transactions và replication slots có thể chặn cleanup.** Tăng cost limit không giải quyết cleanup horizon.
10. **Giám sát cần kết hợp table statistics, progress views, activity, logs và XID age.**
11. **VACUUM thường chủ yếu tạo space có thể tái sử dụng**, không giống VACUUM FULL rewrite relation.
12. **Tuning phải dựa vào workload và đo lường**, bao gồm query latency, I/O, WAL, replication lag và backlog.

Khi hiểu rõ **ngưỡng nào kích hoạt worker, worker được phép tiêu thụ bao nhiêu tài nguyên và điều gì đang ngăn tuple được cleanup**, bạn có thể giữ PostgreSQL khỏe mạnh mà vẫn bảo vệ hiệu năng của ứng dụng.
