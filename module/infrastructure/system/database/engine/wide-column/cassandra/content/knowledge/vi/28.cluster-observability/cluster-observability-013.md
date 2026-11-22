# Chênh lệch bộ đếm theo khoảng đo và tác động khi restart

> **Chương:** Quan sát hệ thống  
> **Mô-đun:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — Apache Cassandra, hệ cơ sở dữ liệu wide-column phân tán.  
> **Trọng tâm:** Đọc đúng các **bộ đếm tích lũy** (counter) theo khoảng thời gian; tính delta, rate, tỷ lệ lỗi; nhận diện reset do node/JVM/exporter restart; tránh kết luận sai khi tổng hợp metric trên nhiều replica, node và datacenter.

Một số chỉ số vận hành Cassandra có dạng **tổng từ khi tiến trình bắt đầu**: số request đã xử lý, timeout, dropped messages, sự kiện compaction hoặc số lần một stage hoàn tất. Nếu dashboard hiển thị giá trị `1.000.000` lúc 10:00 và `1.000.300` lúc 10:01, điều quan trọng thường không phải “hiện có một triệu request” mà là **tăng thêm 300 request trong 60 giây**.

Nhưng lúc node Cassandra **restart**, những bộ đếm trong bộ nhớ/JMX có thể bắt đầu lại từ 0. Nếu dashboard trừ thẳng `C(t_2) - C(t_1)`, một lần restart có thể tạo ra “-999.980 request”, âm một cách vô nghĩa. Nếu lấy tổng bộ đếm của nhiều node rồi mới tính chênh lệch, sự sụt đột ngột của một node còn có thể làm sai cả đồ thị của cluster.

Do đó cần phân biệt:

1. **Counter tích lũy:** chỉ tăng trong vòng đời của cùng một nguồn đo, có thể reset khi nguồn đo bắt đầu vòng đời mới.
2. **Gauge tức thời:** có thể tăng hoặc giảm hợp lệ, ví dụ pending compactions, heap used và số node Up.
3. **Timer/histogram/meter:** cung cấp count, distribution hoặc tốc độ; từng thành phần có semantics riêng.
4. **CQL `counter` của dữ liệu nghiệp vụ:** kiểu dữ liệu lưu trong Cassandra, **khác hoàn toàn** counter của monitoring.

Bài học tập trung vào cách đo đúng và ra quyết định vận hành dưới các tình huống restart, khoảng trống scrape, thay node, compaction/repair và tải đọc/ghi thay đổi.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân loại metric Cassandra/JMX/exporter thành counter, gauge, timer/histogram và rate đã tính sẵn.
- Tính **chênh lệch (delta)** và **tốc độ (rate)** với đơn vị đúng cho một khoảng đo.
- Phát hiện reset do Cassandra restart, JMX exporter restart hoặc thay series ID; hiểu dữ liệu nào không thể suy ngược chính xác.
- Sử dụng `rate()`, `increase()`, `irate()`, `resets()` trong Prometheus khi metric **thực sự là counter**.
- Tổng hợp metric per-node/per-DC đúng thứ tự: **tính rate trên từng series trước, sau đó mới sum**.
- Tránh lấy chênh lệch của gauge, lấy trung bình p99 giữa các node, hoặc nhầm các request nội bộ với API requests.
- Thiết kế dashboard, cảnh báo và runbook kết hợp restart, node health, GC, compaction, repair, CQL và Java Driver.
- Viết kiểm thử số liệu để phát hiện dashboard báo âm hoặc báo 0 giả khi có reset/missing scrape.

## 2. Các loại số liệu trong Cassandra: nhìn tên chưa đủ

### 2.1. Counter (bộ đếm tích lũy)

Một counter monitoring có giá trị \(C(t)\) đại diện cho **tổng số sự kiện đã xảy ra** kể từ mốc khởi tạo của chính nguồn đo.

Ví dụ khái niệm:

- Số read requests đã được metric của một coordinator ghi nhận.
- Số timeout/unavailable của một nhóm thao tác.
- Số dropped messages ở một stage.
- Số tác vụ đã hoàn tất hoặc byte đã được xử lý bởi một cơ chế nào đó, nếu metric tương ứng được xuất dưới dạng counter.

**Thuộc tính:** trong **cùng một vòng đời** (incarnation) và với semantics ổn định, \(C(t_2)\ge C(t_1)\) khi \(t_2>t_1\). Nhưng restart, khởi tạo lại metric registry, rollover hoặc thay nhãn có thể phá tính đơn điệu giữa hai mẫu đo.

Không phải mọi chỉ số có chữ “total”, “count” hoặc “completed” trong tên đều tự động là counter Prometheus chuẩn. Phải kiểm tra kiểu metric và cách exporter lấy mẫu của **phiên bản đang chạy**.

### 2.2. Gauge (giá trị tại thời điểm)

Gauge có thể tăng hoặc giảm đúng theo vận hành:

| Gauge minh họa | Tại sao có thể giảm hợp lệ? |
|---|---|
| Số pending compactions | Tác vụ được thực hiện xong |
| Số active thread/stage tasks | Công việc hoàn tất |
| Heap used / off-heap used | JVM GC hoặc giải phóng bộ nhớ |
| Số kết nối client đang mở | Client đóng kết nối |
| Disk free bytes | Ghi dữ liệu mới làm giảm; cleanup làm tăng |
| Uptime của JVM/node | Restart đưa uptime về gần 0 |

**Không áp dụng `rate(counter)` cho gauge chỉ vì muốn vẽ tốc độ.** Nếu muốn biết tốc độ đổi của gauge thì phải chọn phép tính phù hợp với dữ liệu, hiểu nhiễu và ý nghĩa đơn vị; `delta(gauge[...])` hoặc `deriv()` (khi dùng Prometheus) có mục đích khác hẳn counter rate.

### 2.3. Timer, histogram và meter

Trong hệ metric thường dùng của Cassandra/Java (ví dụ Dropwizard Metrics qua JMX):

- **Timer:** có thể có count tích lũy và phân phối latency (min/max/percentiles), tùy cách xuất JMX.
- **Meter:** có thể có count cùng **one-/five-/fifteen-minute rates** đã tính sẵn.
- **Histogram:** ghi phân bố giá trị, count và quantiles/buckets tùy cách exporter chuyển đổi.
- **Gauge:** giá trị hiện hành, có thể chứa độ trễ/size/rate được tính sẵn.

Đặc biệt:

- `Count` của timer/meter có thể là bộ đếm từ khi process bắt đầu.
- `OneMinuteRate` là **tốc độ đã được ước lượng**, không phải counter cần lấy chênh lệch lần nữa.
- `MeanRate` kiểu từ khi process khởi tạo bị ảnh hưởng bởi tuổi process; nó không tương đương với rate của một cửa sổ 5 phút gần nhất.
- p99 latency đã tính trên một node là **phân vị**, không được lấy trung bình số học giữa các node rồi gọi là p99 toàn cluster.

### 2.4. Phân biệt counter monitoring với cột `counter` trong CQL

Cassandra có kiểu CQL:

```sql
CREATE TABLE IF NOT EXISTS lab_obs.page_views (
    page_id uuid PRIMARY KEY,
    views counter
);

UPDATE lab_obs.page_views
SET views = views + 1
WHERE page_id = 11111111-1111-1111-1111-111111111111;
```

Cột `views counter` là **dữ liệu nghiệp vụ được lưu trên replica** với những semantics riêng của Cassandra counter tables. Nó **không mặc định reset khi JVM Cassandra restart** và không phải một JMX counter. Không áp logic “đếm từ khi tiến trình khởi động” lên dữ liệu đó.

Bài học này nói về **metric counter từ hệ quan sát**, không phân tích chi tiết thiết kế ứng dụng với CQL counter.

## 3. Công thức delta và rate cho một vòng đời ổn định

### 3.1. Chênh lệch tuyệt đối theo khoảng đo

Gọi hai mẫu liên tiếp của một counter là:

- \(C_1=C(t_1)\).
- \(C_2=C(t_2)\).
- \(\Delta t=t_2-t_1>0\), tính bằng giây.

Nếu **cùng process/series, không có reset và không có sai lệch semantic**, ta có:

\[
\Delta C=C_2-C_1
\]

\[
r=\frac{\Delta C}{\Delta t}\quad
\text{(sự kiện/giây)}
\]

Ví dụ: một metric ghi nhận `25.000` read requests ở 10:00 và `25.900` ở 10:03.

\[
\Delta C=25.900-25.000=900
\]

\[
\Delta t=3\times60=180\text{ giây}
\]

\[
r=\frac{900}{180}=5\text{ requests/s}
\]

**Quan trọng:** 5 requests/s là trung bình trong ba phút; không thể suy ra đỉnh một giây của thời gian đó chỉ từ hai mẫu.

### 3.2. Đơn vị phải nhất quán

| Đại lượng | Đơn vị nên trình bày |
|---|---|
| Tổng requests đã xảy ra | requests hoặc events |
| `increase` trong khoảng 5 phút | requests/5 phút |
| `rate` của requests | requests/s |
| Byte ghi tích lũy và chênh lệch byte | bytes hoặc MiB/GiB |
| `rate` byte write | bytes/s hoặc MiB/s |
| Timeout ratio | Phần trăm không đơn vị |
| Latency | ms hoặc s, chọn nhất quán |
| Pending compaction | Số tác vụ (gauge), không phải tasks/s |

Phải phân biệt **MB/s** (10^6 bytes/s) và **MiB/s** (2^20 bytes/s). Đổi đơn vị rõ ràng nếu so thông lượng NIC, streaming và SSTable compaction.

### 3.3. Khoảng đo dài và ngắn

Một khoảng 5 phút thường mượt hơn 30 giây vì có nhiều mẫu hơn, nhưng:

- Khoảng quá **ngắn**: rate dao động mạnh do burst/scrape jitter, nhất là hệ ít request.
- Khoảng quá **dài**: che mất spike và thời điểm restart.
- Dashboard cần cả cửa sổ nhanh cho phát hiện và cửa sổ dài cho xu hướng.
- Nếu có reset trong khoảng, phép trừ thủ công hai đầu **không hợp lệ**; cần xử lý reset-aware và chấp nhận giới hạn suy luận.

Với scrape mỗi 15 giây, cửa sổ 5 phút có khoảng 20 mẫu nếu hệ thu thập hoạt động đều; đó là **ví dụ cấu hình**, không phải bắt buộc cho mọi hệ thống.

## 4. Ví dụ quan trọng: restart làm counter giảm

Giả sử metric đọc của node A được scrape mỗi phút:

| Thời điểm | Giá trị `C` | Uptime node minh họa | Điều đã xảy ra |
|---|---:|---:|---|
| 10:00 | 1.000 | 7.200 s | Process hoạt động bình thường |
| 10:01 | 1.120 | 7.260 s | +120 reads |
| 10:02 | 1.250 | 7.320 s | +130 reads |
| 10:03 | 20 | 20 s | **Node đã restart** trước lần scrape này |
| 10:04 | 140 | 80 s | +120 reads từ sau mẫu 10:03 |
| 10:05 | 270 | 140 s | +130 reads |

### 4.1. Phép trừ mù gây ra giá trị âm

Giữa 10:02 và 10:03:

\[
\Delta C_{\text{naive}}=20-1.250=-1.230
\]

Không có “âm 1.230 reads”. Đây là **reset của bộ đếm in-memory**, không phải tải âm.

Nếu bạn tính:

```text
delta = current - previous

if delta < 0:
    rate = delta / elapsed  # SAI khi counter reset
```

dashboard sẽ có rate âm, biểu đồ sai và cảnh báo/so sánh có thể vô nghĩa.

### 4.2. Sau reset, biết được điều gì?

Nếu counter thực sự reset về 0 khi process khởi động và ở 10:03 đã có 20 reads, ta **quan sát được** 20 reads sau restart. Nhưng trong khoảng từ lần scrape 10:02 đến lúc process dừng, có thể đã xảy ra **những reads khác mà metric cũ không được scrape lần nữa**.

Vì vậy:

- `20` là phần đọc được sau reset tại thời điểm 10:03, không phải tổng chính xác số reads trong toàn phút 10:02–10:03.
- Một công cụ reset-aware có thể **ước lượng** tăng thêm từ các mẫu counter đang có.
- **Không thể khôi phục chính xác mọi sự kiện trong thời gian không quan sát** chỉ từ hai giá trị 1.250 và 20.
- Nếu muốn số lượng events tuyệt đối với yêu cầu kiểm toán, phải dùng log/trace/nguồn sự kiện bền vững, không dựa vào JMX counter resettable.

**Đừng thay số âm bằng 0 rồi tuyên bố phút đó không có request.** Cách `max(0, C_2-C_1)` có thể giấu các reads sau restart và khiến tổng traffic bị thiếu.

### 4.3. Reset có thể do đâu?

| Nguyên nhân | Dấu hiệu | Tại sao cần phân biệt |
|---|---|---|
| Cassandra JVM restart | Uptime về thấp, process start time đổi, node Down/Up | Nhiều JMX/process counters reset cùng lúc |
| Exporter restart | Exporter process time đổi, Cassandra uptime không đổi | Một số counters được exporter tổng hợp có thể reset, nhưng JMX counters trực tiếp có thể không |
| Monitoring/TSDB restart | Scrape gap hoặc chuỗi mẫu bị đứt | Metric trên Cassandra có thể vẫn tiếp tục tăng |
| Node replace/rebootstrap | Host ID/instance/IP/labels thay đổi | Series cũ kết thúc, series mới bắt đầu; không phải tiếp tục cùng nguồn |
| Counter wrap/rollover | Giá trị quay về nhỏ, uptime không đổi | Cần biết độ rộng counter và cách exporter xử lý |
| Đổi exporter/version/metric mapping | Tên/nhãn/đơn vị/semantics thay đổi | Không cộng hai định nghĩa khác nhau như một series |
| Lỗi thu thập/scrape | Mẫu mất/invalid/stale | Không đủ bằng chứng để suy ra restart thực |

Phải kết hợp **process identity, uptime, logs, lifecycle event và kiểu metric**; không suy ngược “node restart” chỉ từ một điểm giảm trên biểu đồ.

## 5. Cách dùng Prometheus với counter

Trong Prometheus, những hàm cơ bản để quan sát counter là `rate()`, `increase()`, `irate()` và `resets()`.

> **Cảnh báo về tên metric:** Tên `cass_read_requests_total`, `cass_read_timeouts_total`, `cass_compaction_written_bytes_total` và `cass_dropped_messages_total` trong các ví dụ **là tên giả định đã được chuẩn hóa**, *không phải* tên chắc chắn có sẵn trong Apache Cassandra. Một exporter JMX khác có thể xuất `org_apache_cassandra_metrics_*` hoặc tên khác, có kiểu/nhãn khác. Trước khi dùng, kiểm tra `/metrics` hoặc cấu hình exporter thực tế và xác nhận các series là counter.

### 5.1. `rate()`: tốc độ trung bình trên một cửa sổ

```promql
rate(cass_read_requests_total{cluster="prod",dc="dc1"}[5m])
```

Kết quả có đơn vị **requests/giây** cho **mỗi time series** còn nhãn tương ứng. `rate()` tính tốc độ trong cửa sổ và có xử lý các **counter resets mà nó thấy giữa những mẫu**. Nó cũng có cơ chế ngoại suy ra ranh giới khoảng đo; vì vậy kết quả có thể là số thập phân ngay cả khi count là số nguyên.

Một cửa sổ không có đủ mẫu hợp lệ có thể không tạo kết quả; đó **không giống với một tốc độ chắc chắn bằng 0**.

### 5.2. `increase()`: số sự kiện tăng trong cửa sổ

```promql
increase(cass_read_requests_total{cluster="prod",dc="dc1"}[5m])
```

Cho mức tăng **xấp xỉ trong 5 phút** theo cách nội suy/reset-aware của Prometheus. Không mặc định kết quả luôn là số nguyên hay bằng đúng số event ứng dụng đã ghi nhận.

Mối quan hệ xấp xỉ khi đều đặn:

\[
\operatorname{increase}(C[5m])
\approx\operatorname{rate}(C[5m])\times300.
\]

`increase` rất hữu ích để lập tổng sự kiện theo cửa sổ; `rate` hữu ích để so throughput theo giây. Cả hai vẫn bị giới hạn bởi việc không quan sát được các events trước restart nằm giữa hai scrape.

### 5.3. `irate()`: rate từ hai mẫu gần nhất

```promql
irate(cass_read_requests_total{cluster="prod",dc="dc1"}[5m])
```

`irate` chủ yếu dựa vào **hai điểm gần cuối**, phù hợp đồ thị nhanh để thấy burst ở hệ có traffic cao, nhưng dễ dao động và có thể không đại diện cả 5 phút. Với cảnh báo SLO cần ổn định, thường ưu tiên `rate` hoặc `increase` trên cửa sổ đủ dài.

### 5.4. `resets()`: xác định giảm giữa các mẫu

```promql
resets(cass_read_requests_total{cluster="prod"}[15m])
```

Hàm này đếm số lần **giảm giá trị counter được quan sát** trong cửa sổ của mỗi series. Nó là dấu hiệu hữu ích để chú thích dashboard, nhưng:

- Không thay thế log restart của Cassandra.
- Không thấy reset nếu **nhãn time series thay đổi và series mới không nối được với series cũ**.
- Không phát hiện chính xác những reset không được scrape ở hai phía.
- Có thể nhận diện rollover/reset của exporter; phải đối chiếu uptime/process identity.

### 5.5. Vì sao không dùng `delta()` cho counter?

`delta()` được thiết kế cho **gauge**, không phải counter có reset. Dùng `delta(counter[5m])` có thể làm số âm khi restart và không xử lý semantics tích lũy đúng cách. Tương tự, `deriv()` biểu thị xu hướng tuyến tính của gauge, không thay thế `rate()` cho counter.

**Nguyên tắc:** kiểm tra kiểu metric trước, rồi mới chọn hàm.

## 6. Tổng hợp đúng thứ tự trên nhiều node và DC

### 6.1. Một node restart sẽ làm hỏng `rate(sum(counter))`

Giả sử DC1 có hai node:

| Thời điểm | Node A | Node B | Tổng counter |
|---|---:|---:|---:|
| 10:00 | 1.000 | 800 | 1.800 |
| 10:01 | 1.120 | 880 | 2.000 |
| 10:02 | **20 sau restart** | 960 | **980** |

Nếu tính tổng tích lũy trước rồi trừ:

\[
\Delta\operatorname{sum}(C)
=980-2.000=-1.020.
\]

**Sai:** không có chuyện DC1 có throughput âm. Hơn nữa việc sum raw counters trên các node có tuổi process khác nhau **không có ý nghĩa về “tổng request từ khi cluster bắt đầu”**.

**Đúng:** tính rate reset-aware theo từng series/node rồi mới cộng rate.

```promql
sum by (cluster, dc) (
  rate(cass_read_requests_total{cluster="prod"}[5m])
)
```

Với `increase`:

```promql
sum by (cluster, dc) (
  increase(cass_read_requests_total{cluster="prod"}[5m])
)
```

Lý do: **mỗi node có reset và vòng đời riêng**. Khi tính theo từng series, phép ước lượng có cơ hội nhận ra điểm giảm của node A mà không khiến raw counter của node B bị hiểu sai.

### 6.2. Những yếu tố phá vỡ phép cộng trên cluster

| Vấn đề | Hậu quả |
|---|---|
| Trùng scrape cùng một JVM từ hai exporters | Double count nếu không lọc/dedupe |
| Một node mất scrape | Tổng rate có thể thấp giả vì thiếu node |
| Node mới thay node cũ nhưng label `instance` khác | Series mới không có lịch sử đủ dài; tạo khoảng trống quan sát |
| Một metric đo coordinator requests, metric khác đo replica reads | Không thể so trực tiếp 1:1 |
| Mỗi DC có nguồn traffic khác nhau | Tổng cluster che mất DC hỏng hoặc được failover |
| Scrape interval/retention khác nhau | Sai lệch khi so rate quá ngắn/không đủ mẫu |
| Metric bị relabel/đổi đơn vị | Đồ thị có discontinuity không do tải thực |
| Nhiều keyspace/table dùng cùng tên metric nhưng nhãn bị loại | Không còn cách phân biệt workload |

Định nghĩa chính xác **đơn vị đếm**: “request client tới coordinator”, “request đến một replica”, “mutation nội bộ”, “stage task”, “byte stream” là các loại sự kiện khác nhau. Replication factor RF=3 không làm mọi client write được đếm đúng ba lần ở cùng metric.

### 6.3. Nhãn (labels) cần có

Một hệ quan sát thường cần phân biệt:

- `cluster`: cụm nào.
- `dc` và `rack`: miền lỗi và đường WAN.
- `host_id` hoặc nhận diện node ổn định, `instance` endpoint scrape.
- `keyspace`/`table` khi metric thực có phạm vi bảng.
- `operation` hoặc `scope`: Read, Write, RangeSlice, CAS, v.v. theo exporter.
- `environment`: lab/staging/production.
- `exporter` và version khi thay pipeline.

**Lưu ý cardinality:** đừng thêm partition key, user ID, request ID hoặc event ID vào nhãn Prometheus cho mỗi mẫu. Điều đó tạo số lượng series khổng lồ và làm TSDB quá tải. Dùng logs/traces có sampling để điều tra trường hợp cá biệt.

### 6.4. Khi node thay thế, đừng “nối liền” bộ đếm như cùng tiến trình

Với node replacement, Cassandra host ID hoặc exporter `instance` có thể đổi. Series mới bắt đầu từ mức nhỏ hoặc không có dữ liệu trước thời điểm bootstrap. Dashboard nên:

1. Ghi lại mốc topology change.
2. Giữ nhận diện node và process incarnation rõ.
3. Xem rate của series mới sau khi đủ scrape samples.
4. So sự thay đổi tổng rate với traffic ứng dụng và node availability.
5. Không suy ra “traffic giảm” khi thực ra một source metric đang không được thu thập.

Một số pipeline có thể dùng nhãn logical role ổn định qua lần thay máy. Điều đó tiện cho dashboard nhưng **không được che mất reset/vòng đời của process**.

## 7. Tỷ lệ lỗi, dropped messages và quy mô tải

### 7.1. Tỷ lệ lỗi phải so đúng mẫu số

Một mục tiêu thường là đo **tỷ lệ timeout trong số read requests**:

\[
\text{timeout ratio}
=\frac{\text{read timeouts trong khoảng}}
{\text{read attempts trong cùng khoảng}}\times100\%.
\]

Điều kiện:

- Numerator và denominator phải đo **cùng lớp** (client coordinator hay driver) và cùng loại request.
- Có cùng phạm vi `cluster/dc/operation`.
- Không trộn “số lần retry” ở driver với “số request đã đến một node” nếu chưa hiểu cách đếm.
- Trong khoảng tải bằng 0, ratio **không xác định**; không coi tự động là 0% và báo “dịch vụ khỏe”.

Ví dụ minh họa cho metric chuẩn hóa:

```promql
sum by (cluster, dc) (
  rate(cass_read_timeouts_total{cluster="prod"}[5m])
)
/
clamp_min(
  sum by (cluster, dc) (
    rate(cass_read_requests_total{cluster="prod"}[5m])
  ),
  0.001
)
```

Hàm `clamp_min` tránh chia 0, **nhưng cũng có thể làm tỷ lệ ở rất ít traffic bị sai lệch**. Trong alert thực tế cần thêm điều kiện **mẫu đủ lớn** và xác nhận metric timeout là tập con phù hợp của request metric:

```promql
(
  sum by (cluster, dc) (
    increase(cass_read_timeouts_total{cluster="prod"}[5m])
  )
  /
  clamp_min(
    sum by (cluster, dc) (
      increase(cass_read_requests_total{cluster="prod"}[5m])
    ),
    1
  )
) > 0.02
and on (cluster, dc)
sum by (cluster, dc) (
  increase(cass_read_requests_total{cluster="prod"}[5m])
) > 100
```

Đây là **công thức minh họa**, không phải ngưỡng SLO khuyến nghị. Ngưỡng 2%/100 requests cần được thay bằng tiêu chí nghiệp vụ, quan sát từ driver và semantics exporter.

### 7.2. Dropped messages là dấu hiệu áp lực, không nhất thiết bằng request lỗi

Các stage trong Cassandra có thể có metric dropped messages. Counter tăng cho thấy một số message bị drop theo semantics stage, nhưng:

- Không phải mọi message drop đều là một API request lỗi.
- Một request có thể có nhiều message hoặc retry.
- Không phải mọi timeout đều đi kèm đúng một dropped message.
- Stage/tên metric và cách đếm khác theo Cassandra version.

Nên xem **rate dropped theo stage**, kèm pending/blocked queues, GC, disk I/O, client p99/timeout. Một lần restart làm dropped counter về 0 **không có nghĩa vấn đề hiệu năng đã biến mất**.

### 7.3. Latency p99: đừng lấy trung bình các p99

Giả sử node A p99=20 ms, node B p99=500 ms. Trung bình `260 ms` **không phải** p99 toàn cluster. Phân vị không cộng tuyến tính và phụ thuộc số lượng cùng phân phối request.

Nếu exporter thật sự xuất **histogram buckets có nhãn `le` và cùng cấu hình buckets**, có thể tính phân vị toàn DC theo tổng tốc độ bucket:

```promql
histogram_quantile(
  0.99,
  sum by (dc, le) (
    rate(cass_read_latency_seconds_bucket{cluster="prod"}[5m])
  )
)
```

**Điều kiện bắt buộc:** series `..._bucket` phải **tồn tại và là cumulative histogram bucket counters**. Không thể dùng công thức này cho một JMX timer chỉ xuất `p99` gauge hoặc snapshot quantiles. Với JMX timer thuần quantiles, hãy trình bày per-node p99 hoặc tính phân phối từ dữ liệu/histogram đủ điều kiện; **không cộng/trung bình các quantiles đã tính sẵn**.

## 8. Khoảng trống scrape, stale series và mất dữ liệu quan sát

### 8.1. Bốn trường hợp phải phân biệt

| Trường hợp | Điều có thể thấy | Kết luận đúng |
|---|---|---|
| Traffic thực sự bằng 0 | Counter không đổi, scrape liên tục thành công | Trong khoảng quan sát đó rate có thể bằng 0 |
| Node Down | Scrape `up=0` hoặc không có mẫu; node unavailable | Thiếu metric, không đồng nghĩa không có requests ở cả cluster |
| Endpoint exporter lỗi | `up=0`, nhưng Cassandra có thể vẫn phục vụ CQL | Lỗi observability, phải xác minh qua node/log/client |
| Node/Pod được thay, nhãn đổi | Series cũ stale, series mới xuất hiện | Phải nối timeline sự kiện, không suy ra 0 traffic |

`up` là metric của Prometheus cho biết **scrape target có thành công**, không phải một kiểm chứng Cassandra luôn khỏe. Node có thể trả metrics nhưng CQL unavailable, hoặc CQL còn hoạt động trong khi exporter chết.

### 8.2. Vì sao không dùng `or vector(0)` tùy tiện?

Một truy vấn thiếu samples thường tạo ra **no data**. Nếu ép nó thành 0 vô điều kiện, dashboard có thể vẽ “0 timeouts, 0 reads” khi thực tế exporter bị mất hoặc node hỏng. Điều đó che sự cố thu thập.

Một thiết kế giám sát tốt tách:

1. **Service availability:** driver/CQL SLO, quorum, errors.
2. **Telemetry availability:** scrape targets, mẫu mới nhất, exporter health.
3. **Metric values:** read/write rate, latency, dropped messages, compaction.

Mất metric là một trạng thái cần cảnh báo riêng nếu dữ liệu đó quan trọng cho vận hành.

### 8.3. Interpolation không tái tạo chính xác dữ liệu đã mất

Prometheus tính rate bằng các mẫu đang có, xử lý counter decreases và ngoại suy ra ranh giới cửa sổ. Nhưng nếu node vừa ghi 2.000 requests rồi restart giữa hai lần scrape, nguồn quan sát **không còn số cũ ngay trước restart**. TSDB không thể biết các events đó từ một counter đã reset.

Nếu cần độ chính xác kiểm toán cho doanh thu, giao dịch hoặc sự kiện xóa, **bộ đếm process không đủ**. Dùng event log bền vững, transaction/audit source, CDC hoặc hệ thống khác có cơ chế hoàn tác/replay và bảo toàn dữ liệu phù hợp.

### 8.4. Time skew và sample timestamps

Nếu scrape khác node ở các thời điểm lệch nhau, dashboard cộng rate trên cửa sổ đo chung vẫn là **ước lượng**, không phải đếm chính xác những events trong cùng mili giây. NTP/synchronization, scrape interval, jitter và remote-write delay đều quan trọng.

Với Cassandra, đồng bộ thời gian hệ thống còn ảnh hưởng timestamp reconciliation của dữ liệu, nhưng đó là **một vấn đề khác** với tính đúng đắn của nhãn/time series.

## 9. Nhận diện restart một cách đáng tin cậy

### 9.1. Kết hợp ít nhất hai nguồn bằng chứng

Một cách xác nhận node Cassandra restart:

- **JVM uptime** trở về thấp, hoặc process start timestamp thay đổi nếu metric có sẵn.
- **Log Cassandra** ghi sự kiện shutdown/startup cùng host ID.
- **Node status** chuyển `UN → DN/không phản hồi → UJ/UN` tùy trạng thái.
- Một hoặc nhiều **process-scoped counters** giảm đồng thời.
- **Monitoring/external system** có lịch khởi động lại host, Kubernetes/container restart count hoặc sự kiện deploy.

Nếu chỉ có một counter giảm, có thể là exporter reset/metric relabel. Nếu chỉ có `up=0`, có thể chỉ là scrape thất bại.

### 9.2. Query minh họa phát hiện reset

```promql
resets(cass_read_requests_total{cluster="prod"}[30m]) > 0
```

Với process start time gauge **nếu thực có**:

```promql
changes(process_start_time_seconds{job="cassandra"}[30m]) > 0
```

**Cảnh báo:** metric `process_start_time_seconds` của một exporter riêng có thể phản ánh **process exporter**, không phải JVM Cassandra. Cần kiểm tra nó đo tiến trình nào trước khi diễn giải. Cassandra/JMX uptime của JVM hoặc event logs có thể đáng tin hơn trong trường hợp exporter chạy ngoài JVM.

### 9.3. Một restart khác với thay node

**Restart trên cùng node:** host ID Cassandra thường giữ nguyên nếu dữ liệu/system keyspace vẫn được bảo toàn; metric registry in-process có thể reset.

**Replace node:** host ID, địa chỉ và tập token/role có thể thay đổi theo phương pháp replacement; nhiều time series cũ kết thúc và series mới bắt đầu. Đây là **thay đổi membership**, cần kiểm tra RF và replica placement, không chỉ annotate một restart.

Đừng tự “ghép” counter của host cũ với host mới để tạo đường tích lũy liên tục; semantics nguồn đã thay đổi.

## 10. JMX và nodetool: đọc giá trị thô sao cho đúng?

### 10.1. Các lệnh quan sát thường gặp

Trong môi trường lab hoặc cluster có quyền phù hợp:

```bash
nodetool status
nodetool info
nodetool tpstats
nodetool compactionstats
nodetool tablestats lab_obs.events_by_account
nodetool tablehistograms lab_obs events_by_account
```

Các lệnh trên có mục đích khác nhau:

| Công cụ/chỉ số | Ý nghĩa chính | Cách sử dụng đúng |
|---|---|---|
| `nodetool info` | Tình trạng node, uptime và thông tin hiện hành theo phiên bản | Kiểm tra mốc vòng đời process |
| `nodetool tpstats` / Completed | Tổng công việc đã hoàn tất ở stage; thường scoped theo vòng đời đo | Lấy mẫu nhiều lần và xét restart |
| `nodetool tpstats` / Active, Pending | Giá trị đang hoạt động/đợi | **Gauge**, không xử lý như counter |
| `nodetool tpstats` / Dropped | Số message bị drop theo stage | Nếu là counter trong bản đang chạy, tính delta/rate và xét reset |
| `nodetool compactionstats` / pending | Số việc compaction đang chờ | Gauge, cần đo xu hướng và bối cảnh |
| `nodetool tablestats` | SSTable, disk, read/write stats theo table | Xác minh loại metric và thời gian tích lũy |
| `nodetool tablehistograms` | Phân phối độ trễ/kích thước theo bảng | Không lấy chênh lệch quantile như counter |
| JMX metrics | Count/Rate/Timer/Histogram/Gauge | Xem loại mbean/attribute trước khi tạo query |

Không giả định tên field hay giá trị mặc định giống nhau trên mọi bản Cassandra. `nodetool` là góc nhìn tại node đang gọi; đọc `tpstats` trên node A **không** cho bạn counter của node B.

### 10.2. Giới hạn khi “chụp bảng” thủ công

Giả sử operator chạy:

```text
10:00  nodetool tpstats  Completed=200000
10:05  nodetool tpstats  Completed=205000
```

Nếu đúng cùng node/stage, không restart và metric là counter, tốc độ trung bình 5 phút:

\[
r=\frac{205.000-200.000}{5\times60}
=\frac{5.000}{300}\approx16{,}67\text{ tasks/s}.
\]

Nhưng nếu trong 5 phút node restart, phép trừ có thể âm hoặc đánh giá thiếu dữ liệu. Khi lấy mẫu thủ công, cần ghi đồng thời **timestamp, node ID, uptime, stage, version và status**, không chỉ chụp con số Completed.

### 10.3. Chỉ số của replica và coordinator không giống nhau

Một API read từ ứng dụng Java có thể được coordinator chuyển tới một hoặc nhiều replica theo CL/topology. Tùy metric:

- Client request count tại coordinator có thể đếm một lần cho request nhận được.
- Replica/internal read stage count có thể đếm nhiều công việc từ một request.
- Timeout metric có thể ghi nhận khi coordinator quyết định request thất bại.
- Java Driver có thể đã retry sang coordinator khác, khiến một action ứng dụng tạo nhiều attempts.

Không dùng một hệ số nhân cố định RF=3 để chuyển tất cả metric per-node thành requests của ứng dụng. Trước mỗi dashboard tỷ lệ lỗi, phải xác nhận **metric nào đếm attempts, completions, retries và internal tasks**.

## 11. Dashboard và cảnh báo có tính đến restart

### 11.1. Dashboard nên chia thành bốn vùng

**Vùng A — Tải và lỗi**

- Read/write requests/s theo DC, node và operation.
- Timeout/failure/unavailable rate và ratio với mẫu số hợp lệ.
- Driver client p95/p99, retry count, pool/connection status.

**Vùng B — Sức khỏe node/replica**

- `status` và số full replicas sẵn sàng theo keyspace/DC.
- JVM uptime/process start/restart events, heap/GC, CPU.
- Scrape success, metric staleness, exporter version.

**Vùng C — SSTable và nền**

- Pending/active compactions, SSTable count, disk used/free, tombstone warnings.
- Repair/streaming status, bytes/s, backlog và thất bại.
- Dropped messages/stage backlog, thread pool saturation.

**Vùng D — Độ tin cậy của dữ liệu quan sát**

- Số series/node đang được scrape so với inventory/topology thực.
- Counter resets theo giờ/ngày.
- Các khoảng `no data`, scrape jitter và exporter rollouts.
- Ghi chú deploy/restart, node replacement, bootstrap/decommission.

### 11.2. Cảnh báo kết hợp, không dựa vào một counter

Ví dụ: read timeout rate tăng cùng client p99 và pending compaction. Khi counter reset, alert không nên tắt chỉ vì giá trị raw timeout thấp lại; phải dùng `rate` và đánh giá telemetry health.

Một bảng quyết định:

| Tín hiệu | Có thể là nguyên nhân | Hành động |
|---|---|---|
| Raw Count giảm, uptime reset | JVM restart | Annotate restart, kiểm tra recovery và rate sau đủ samples |
| Raw Count giảm, uptime không đổi, exporter restart | Metric pipeline reset | Kiểm tra exporter mapping/series identity |
| Rate reads giảm, `up=0` | Mất scrape/endpoint | Điều tra telemetry và Cassandra health độc lập |
| Timeout rate tăng, p99 tăng, disk gần bão hòa | IO/compaction contention | Kiểm tra `compactionstats`, SSTable/tombstone, disk |
| Dropped rate tăng, pending threads tăng | Stage bottleneck | Kiểm tra GC/CPU/latency và tải nền |
| Rate cụm thấp khi một node bị thay | Series churn hoặc mất traffic thật | So driver QPS, ring, nhãn và restart |
| No data nhưng dashboard “0 timeouts” | Có thể đã ép no-data thành 0 | Sửa query và alert metric availability |

### 11.3. Lựa chọn cửa sổ cho cảnh báo

- Tín hiệu nhanh: 1–5 phút cho triệu chứng cấp tính (tùy QPS và scrape interval).
- Xu hướng: 15–60 phút cho capacity, compaction debt và tốc độ tăng lỗi bền vững.
- SLO/error budget: khoảng dài hơn theo chính sách dịch vụ.
- Restart annotation: khoảng vừa đủ thấy thay process và trạng thái sau phục hồi.

Nếu một cửa sổ có **quá ít samples hoặc quá ít requests**, kết quả tỷ lệ có thể rất nhiễu. Điều kiện số mẫu tối thiểu/traffic tối thiểu và cảnh báo mất telemetry giúp tránh false positives.

## 12. Tình huống thực tế: đọc/ghi, compaction và repair

### 12.1. “Sau restart, dropped messages trở về 0 — lỗi đã hết?”

Không. Bộ đếm dropped có thể reset cùng JVM. Kiểm tra:

1. Cassandra uptime và log restart.
2. `rate(dropped_messages_total[...])` ở thời điểm sau restart đủ samples.
3. Pending/active stages, CPU, GC, disk, client timeout/p99.
4. Repair/compaction/bootstrap có đang gây nghẽn không.

Nếu dropped rate tăng trở lại sau vài phút, nguyên nhân tải chưa được giải quyết. Việc raw counter về 0 chỉ là **đổi mốc tích lũy**.

### 12.2. “Compaction tăng rất nhanh nhưng disk free giảm”

Phải tách:

- `compaction bytes written total` (counter, nếu exporter cung cấp).
- `pending compactions` (gauge).
- `disk free bytes` (gauge).
- SSTable version/tombstone, snapshot và file output tạm.

Một giai đoạn compaction có thể ghi lại nhiều byte và tạo tệp output trước khi giải phóng input, làm free disk giảm tạm thời. Không suy “compaction tăng => dữ liệu ứng dụng mới tăng cùng tỷ lệ”.

Khi Cassandra restart, compaction counters có thể reset nhưng **SSTable bytes trên đĩa không đột nhiên về 0**. Đây là ví dụ rõ nhất để phân biệt metric vòng đời process và trạng thái lưu trữ bền vững.

### 12.3. “Repair hoàn tất sau restart, nhưng metric reset”

Một job repair có thể bị ngắt hoặc có trạng thái server-side đặc thù khi node restart. Raw counters về 0 không chứng minh repair thành công hay bị xóa khỏi lịch.

Cần xem job/session history, `nodetool repair_admin` nếu phiên bản hỗ trợ, token ranges/replicas bao phủ, validation/streaming/finalization logs và trạng thái cuối. **Repair completion phải dựa vào workflow/session**, không dựa vào `Completed` tổng trong `tpstats`.

### 12.4. “QPS trung bình toàn DC giảm sau bootstrap”

Có ba khả năng phải phân biệt:

1. Lưu lượng ứng dụng thật sự giảm.
2. Load được chia sang node mới nhưng dashboard bỏ sót nhãn/node mới.
3. Node cũ bị retire, series cũ stale và query tổng không đủ sample.

Đối chiếu application/driver QPS, per-node rate, inventory nodes theo DC và scrape target health. Chỉ khi các series/semantics phù hợp mới kết luận về thay đổi tải.

## 13. Bài lab CQL để quan sát theo khoảng đo

### 13.1. Chuẩn bị bảng sự kiện thường, không dùng CQL counter

Ví dụ tạo bảng trên môi trường lab có DC tên `dc1` và đủ replica cho RF=3:

```sql
CREATE KEYSPACE IF NOT EXISTS lab_obs
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE IF NOT EXISTS lab_obs.events_by_account (
    account_id uuid,
    event_id timeuuid,
    event_type text,
    payload text,
    PRIMARY KEY ((account_id), event_id)
) WITH CLUSTERING ORDER BY (event_id DESC);
```

### 13.2. Tạo workload có phạm vi nhỏ

```sql
CONSISTENCY LOCAL_QUORUM;

INSERT INTO lab_obs.events_by_account (
    account_id, event_id, event_type, payload
) VALUES (
    11111111-1111-1111-1111-111111111111,
    7c627d5a-a6b0-11ef-8ae8-0242ac120002,
    'created',
    'sample'
);

SELECT event_id, event_type
FROM lab_obs.events_by_account
WHERE account_id = 11111111-1111-1111-1111-111111111111
LIMIT 20;
```

Chạy một số lần ở mức an toàn cho lab, rồi quan sát read/write metrics tại coordinator/driver. Mục đích là thấy **counter tăng theo thời gian**, không phải benchmark QPS bằng vài câu lệnh thủ công.

### 13.3. Thu mẫu trước và sau restart có kiểm soát

Trong **lab được phép restart**:

1. Ghi timestamp, node, JMX counter và uptime từ nguồn metric thật.
2. Phát sinh workload nhẹ, thu thêm hai đến ba mẫu trong vài phút.
3. Restart đúng một node trong lab theo quy trình thích hợp; **không restart production chỉ để kiểm thử**.
4. Thu tiếp uptime/process start, raw counter và logs từ cùng node.
5. So phép trừ naïve với cách đánh dấu reset; xem kết quả `rate`/`resets` nếu có Prometheus.
6. Xác minh scrape `up` và chuỗi time series có bị đổi nhãn.
7. Kiểm tra cluster/RF/CL sau restart để bảo đảm workload vẫn có thể chạy.

Tạo phiếu đo:

| Thời gian | Node ID | Uptime | Counter read | Delta hợp lệ? | Rate | Ghi chú |
|---|---|---:|---:|---|---:|---|
| T0 | A | 3.600 s | 1.000 | Chưa có mẫu trước | — | Baseline |
| T+60s | A | 3.660 s | 1.150 | Có: +150 | 2,5 req/s | Cùng process |
| T+120s | A | 12 s | 15 | **Không trừ trực tiếp** | Ước lượng/không đủ | Restart |
| T+180s | A | 72 s | 165 | Có: +150 | 2,5 req/s | Process mới |

**Các số là dữ liệu minh họa**, không phải output mặc định của `nodetool`. Nhìn T+120: “counter giảm” là reset, không có phép trừ đầy đủ đáng tin để đo tổng requests trong cửa sổ bị cắt.

### 13.4. Bài test alert

Kiểm tra ba tình huống:

- Counter đứng yên với scrape tốt và workload thực sự dừng: rate tiến về 0 đúng.
- JVM restart: không báo traffic âm, có event/reset annotation, không tuyên bố mất sự kiện chính xác bằng giá trị nào.
- Exporter/scrape down trong khi Cassandra vẫn phục vụ: dashboard thể hiện **no data** và alert telemetry health thay vì giả 0 errors.

## 14. Java: xử lý hai mẫu counter và nhận diện restart

Một ứng dụng Java có thể dùng Cassandra Java Driver để phát sinh và đo request, nhưng **JMX metrics là một luồng quan sát riêng**. Dưới đây là ví dụ Java thuần minh họa cách kiểm tra hai mẫu counter trước khi tính delta. Nó **không** cố tái tạo dữ liệu đã mất lúc restart.

```java
import java.time.Instant;
import java.time.Duration;
import java.util.OptionalDouble;

public final class CounterInterval {
    static final class Sample {
        final String nodeId;
        final Instant time;
        final long processStartEpochSeconds;
        final long count;

        Sample(String nodeId, Instant time,
               long processStartEpochSeconds, long count) {
            this.nodeId = nodeId;
            this.time = time;
            this.processStartEpochSeconds = processStartEpochSeconds;
            this.count = count;
        }
    }

    static OptionalDouble ratePerSecond(Sample before, Sample after) {
        long elapsedMillis =
            Duration.between(before.time, after.time).toMillis();

        if (elapsedMillis <= 0 || before.count < 0 || after.count < 0) {
            return OptionalDouble.empty();
        }
        // Different node or process: cannot subtract cumulative totals.
        if (!before.nodeId.equals(after.nodeId)
                || before.processStartEpochSeconds
                   != after.processStartEpochSeconds) {
            return OptionalDouble.empty();
        }
        // A decrease may mean reset, rollover or measurement pipeline issue.
        if (after.count < before.count) {
            return OptionalDouble.empty();
        }

        double seconds = elapsedMillis / 1000.0;
        return OptionalDouble.of(
            (after.count - before.count) / seconds);
    }

    public static void main(String[] args) {
        Sample s1 = new Sample(
            "node-A", Instant.parse("2026-11-21T10:00:00Z"),
            1795230000L, 1000L);
        Sample s2 = new Sample(
            "node-A", Instant.parse("2026-11-21T10:01:00Z"),
            1795230000L, 1120L);
        Sample s3 = new Sample(
            "node-A", Instant.parse("2026-11-21T10:02:00Z"),
            1795236060L, 20L); // Different process incarnation

        System.out.println(ratePerSecond(s1, s2));
        // OptionalDouble[2.0]

        System.out.println(ratePerSecond(s2, s3));
        // OptionalDouble.empty: the interval crosses a restart
    }
}
```

**Điểm học:** code này **cố ý trả `empty`** cho khoảng có restart, thay vì phát minh một số rate chính xác. Nếu dùng Prometheus, `rate` có thể đưa ra **ước lượng reset-aware** từ chuỗi nhiều mẫu; hai hướng xử lý không mâu thuẫn: một bên là tính delta chắc chắn của **hai mẫu cùng process**, bên kia là ước lượng cho **chuỗi time series**.

Để dùng trong hệ thật:

- Lấy `nodeId`/process start từ nguồn đáng tin và bảo đảm không nhầm exporter process với Cassandra JVM.
- Kiểm tra value unit, timestamps, duplicate/out-of-order samples.
- Không trộn counter sources hoặc metric semantics giữa các version.
- Trả trạng thái `UNKNOWN/RESET/STALE` cùng giá trị, không chỉ số double; hiện tại code dùng `OptionalDouble` để minh họa tối giản.
- Khi tổng hợp, tính rate riêng từng node rồi mới sum; giữ lại nhãn DC/cluster.
- Với metric monotonic được lưu bền qua restart (nếu có), **không áp quy tắc reset theo JVM một cách máy móc**: phải dựa vào semantics cụ thể.

### 14.1. Java Driver: workload và telemetry khác nhau

Ví dụ Java Driver 4.x gửi truy vấn có partition key đúng để so với request metrics:

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import java.net.InetSocketAddress;
import java.util.UUID;

public final class CassandraReadWorkload {
    public static void main(String[] args) {
        UUID accountId = UUID.fromString(
            "11111111-1111-1111-1111-111111111111");

        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {
            PreparedStatement ps = session.prepare(
                "SELECT event_id, event_type FROM lab_obs.events_by_account " +
                "WHERE account_id = ? LIMIT 20");

            BoundStatement stmt = ps.bind(accountId)
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);
            session.execute(stmt);

            // Read client-side driver metrics and Cassandra JMX metrics
            // through separate configured monitoring exporters.
            // One successful execute() does not establish a 1:1 mapping
            // to every internal node counter.
        }
    }
}
```

**Lưu ý:** đoạn mã không tự lấy JMX counter từ Cassandra; phải có exporter/JMX client hoặc hệ monitoring được cấp quyền. Đọc một dòng CQL không đo được byte compaction, dropped messages hay trạng thái replica ở node khác.

## 15. Thực hành phân tích trên bộ số liệu nhỏ

### 15.1. Tính rate trước restart

Node A ghi nhận:

| Mốc | Reads count |
|---|---:|
| 14:00 | 50.000 |
| 14:05 | 51.200 |

Không có restart, khoảng đo 300 giây:

\[
\Delta C=1.200,\qquad r=1.200/300=4\ \text{reads/s}.
\]

Nếu ứng dụng đếm 1.000 logical reads trong khoảng đó, không mặc định hai chỉ số phải bằng nhau: có retries, internal requests hoặc scope count khác nhau.

### 15.2. Rate và ratio cần cùng phạm vi

Giả sử DC1 có trong 5 phút:

- 6.000 client read attempts từ metric đáng tin.
- 120 read timeouts, tương ứng cùng tập attempts.
- 5.880 read completions theo cùng định nghĩa.

Khi đó:

\[
\text{Read QPS}=6.000/300=20\text{ requests/s}
\]

\[
\text{Timeout ratio}=120/6.000=0{,}02=2\%.
\]

Nếu timeout counter bị reset giữa khoảng và chỉ số 120 là **chênh lệch thô không điều chỉnh**, kết quả 2% không đáng tin. Phải xác nhận ngữ nghĩa và nguồn dữ liệu trước khi tính SLO.

### 15.3. So sánh hai node có tuổi process khác nhau

| Node | Raw count | Rate trong 5 phút |
|---|---:|---:|
| A, uptime 4 ngày | 5.000.000 | 80 req/s |
| B, vừa restart 20 phút | 15.000 | 60 req/s |

Tổng raw count = 5.015.000 **không cho biết** traffic hiện tại hoặc traffic kể từ khi cluster khởi động. Tổng rate đúng theo nghĩa “hai series tương ứng, cùng metric” là **140 req/s**. Việc A có 5 triệu không làm A “tải gấp 333 lần B” ở thời điểm này.

### 15.4. Tác động của một lần mất scrape

Đo 5 phút theo lịch, một node không có mẫu suốt 3 phút. Có thể không tính được rate có độ tin cậy theo cùng quy tắc với các node còn lại. Hãy báo:

- Số node có metric đạt chất lượng / tổng node dự kiến.
- Số samples và khoảng trống quan sát.
- Total estimated QPS kèm **độ bao phủ telemetry**.
- Cảnh báo khi node scrape mất lâu, kể cả khi application SLO chưa hỏng.

Không tự nâng tổng của 4/5 node lên 5/5 bằng hệ số `5/4` nếu phân bố workload theo node không đều.

## 16. Checklist thiết kế dashboard có chịu được restart

**Nguồn và ngữ nghĩa**

- [ ] Mọi metric được phân loại counter/gauge/timer/histogram/meter rõ ràng.
- [ ] Ghi rõ metric scope: coordinator, replica, client driver, node, table, DC.
- [ ] Đơn vị (events, seconds, bytes), label và exporter mapping được xác minh.
- [ ] Biết process/host identity và version; phân biệt node restart với exporter restart.
- [ ] Không nhầm CQL `counter` với monitoring counter.

**Query và số học**

- [ ] Tính `rate/increase` riêng từng counter series **trước** khi tổng hợp theo DC/cluster.
- [ ] Không trừ raw counter xuyên restart và không dùng `delta()` trên counter.
- [ ] Có `resets()` hoặc dấu hiệu tương đương để annotate restart; không coi mỗi reset là một node restart chắc chắn.
- [ ] Dùng cửa sổ đo đủ samples; không diễn giải `no data` thành “0 events”.
- [ ] Error ratio dùng tử số/mẫu số cùng nghĩa và bảo đảm đủ traffic.
- [ ] Không lấy trung bình các p99; chỉ tính histogram quantile hợp lệ nếu có buckets tương thích.

**Vận hành**

- [ ] Dashboard thể hiện node/DC Up/Down, JVM uptime, scrape health và restart events.
- [ ] Có nhóm compaction/repair/tombstone/disk để điều tra nguyên nhân tăng lỗi.
- [ ] Có khả năng phân biệt stream/rebalance khi bootstrap/decommission với tải ứng dụng.
- [ ] Alerts đã được thử với process restart, exporter restart, scrape gaps và label churn.
- [ ] Có runbook kiểm tra CQL/Java Driver để đối chiếu metrics với triệu chứng thực.
- [ ] Đã xác nhận data retention, sampling và label cardinality nằm trong khả năng TSDB.

## 17. Câu hỏi và bài tập

**Bài 1 — Delta đơn giản.** Counter read của một node tăng từ 17.000 lên 18.800 sau 6 phút, không có restart. Tính delta và requests/s trung bình.

**Bài 2 — Reset.** 12:00 counter=4.800; 12:01 counter=4.950; 12:02 counter=30 và JVM uptime=20 giây. Vì sao phép tính `30 - 4.950` sai? Điều gì không thể suy ra chính xác?

**Bài 3 — Tổng hợp.** A từ 1.000 lên 1.100, B từ 800 lên 900, sau đó A restart và count còn 15. Nếu lấy `rate(sum(C))` có rủi ro gì? Thay bằng cách tính nào?

**Bài 4 — Gauge.** `PendingCompactions` giảm từ 12 xuống 3 sau 5 phút. Có phải đây là “negative counter event rate” không? Nên giải thích thế nào?

**Bài 5 — Chọn PromQL.** Cần tổng read QPS của `dc2`. Chọn đúng giữa hai phương án: `sum(rate(metric[5m]))` trên các series của dc2, hay trừ raw tổng count giữa hai snapshots?

**Bài 6 — Tỷ lệ timeout.** Trong 10 phút có 2.000 read attempts và 16 timeouts, cùng nguồn và không mất scrape. Tính timeout ratio và QPS.

**Bài 7 — Không có data.** Dashboard báo 0 read errors từ khi exporter ngừng scrape nhưng Java Driver ghi nhận nhiều timeout. Đây là lỗi gì về thiết kế query/cảnh báo?

**Bài 8 — p99.** Một node có p99=10 ms, node khác có p99=200 ms và lượng requests rất khác nhau. Vì sao \((10+200)/2=105\) ms không phải p99 toàn DC? Cần dữ liệu nào để tính?

**Bài 9 — Restart đồng thời.** Sau deploy, cả ba node của một rack có raw dropped count gần 0. Những bằng chứng nào cần trước khi kết luận “pressure đã biến mất”?

**Bài 10 — Counter nghiệp vụ.** Một bảng CQL có cột `views counter`; JVM restart. Có nên kỳ vọng `views` về 0 như JMX request counter không? Giải thích.

### Gợi ý đáp án

1. Delta `1.800`; thời gian `360` giây; rate `5 req/s`.
2. Counter reset trong vòng đời mới. Số event giữa lần scrape cũ và thời điểm restart có thể không được quan sát, nên không khôi phục chính xác tổng trong phút đó.
3. Node reset làm raw tổng sụt và tạo delta âm; tính `rate` riêng từng series rồi `sum`.
4. Không, đó là gauge giảm vì backlog được xử lý; xem xu hướng và rate compaction/output nếu có metric tương ứng.
5. `sum by(dc)(rate(metric{dc="dc2"}[5m]))` với các series là counter hợp lệ.
6. Ratio `16/2.000=0,8%`; QPS `2.000/600≈3,33 req/s`.
7. “Missing telemetry” bị gán thành 0 errors; phải alert scrape failure và không che `no data`.
8. Percentile không cộng/trung bình tuyến tính; cần phân phối/histogram buckets tương thích hoặc raw observations.
9. Uptime, logs, `resets()`, scrape health, dropped **rate** sau khi đủ samples, pending stages, GC và client p99.
10. Không. `counter` trong CQL là dữ liệu lưu bền có semantics replica, không phải JMX metric đếm trong vòng đời JVM.

## 18. Kết luận

- **Bộ đếm monitoring có ý nghĩa theo chênh lệch và cửa sổ thời gian**, không phải chỉ nhìn số tích lũy.
- Với hai mẫu trong cùng vòng đời, \(\Delta C=C_2-C_1\) và \(r=\Delta C/\Delta t\); **restart phá giả định** đằng sau phép trừ.
- **`rate()` và `increase()` có xử lý reset được quan sát** nhưng vẫn là ước lượng từ các mẫu có sẵn; chúng không tái tạo chính xác sự kiện bị mất giữa các lần scrape.
- **Tính rate trên từng series trước khi sum** theo node/DC/cluster. Không cộng raw counters xuyên nhiều process có tuổi khác nhau để tìm throughput.
- **Counter, gauge, timer/histogram, meter và CQL `counter` là những loại dữ liệu khác nhau.** Nhận diện loại metric trước khi chọn phép tính.
- **No data không bằng zero traffic**. Cần giám sát sự sẵn sàng của pipeline metrics song song với Cassandra/Java Driver.
- Khi restart, bootstrap, replace hoặc repair, phải liên kết các thay đổi metric với **JVM uptime, logs, token/topology, CL, compaction và trạng thái client**, thay vì đoán từ một đồ thị.
- Một dashboard đáng tin không chỉ vẽ đường đẹp; nó công khai **phạm vi, đơn vị, mức bao phủ và độ tin cậy của dữ liệu đo** để hỗ trợ quyết định vận hành.
