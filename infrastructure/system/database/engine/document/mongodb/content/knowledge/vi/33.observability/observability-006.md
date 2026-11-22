# Database profiler và chi phí thu thập thông tin truy vấn trong MongoDB

> **Module:** Database Engine Document MongoDB  
> **Chương:** Quan sát hệ thống  
> **Bài học:** Database profiler và chi phí thu thập thông tin truy vấn

## 1. Vấn đề: thu thập càng nhiều, hệ thống có luôn được quan sát tốt hơn?

Một API bán hàng sử dụng MongoDB có độ trễ p95 tăng đột biến. Nhóm vận hành muốn xác định:

- Query nào chậm, ở database và collection nào?
- Query quét bao nhiêu document, bao nhiêu index key?
- Nó dùng `COLLSCAN` hay `IXSCAN`?
- Truy vấn nào có cùng shape và lặp lại nhiều lần?
- Khi ứng dụng gọi `find()` và `getMore`, thời gian thực thi nằm ở bước nào?
- Làm sao lấy bằng chứng đúng thời điểm mà không làm MongoDB chậm hơn?
- Có nên bật profiler level 2 để ghi tất cả operations?
- Vì sao `system.profile` đôi khi rỗng dù server log chứa `Slow query`?
- Dữ liệu filter/update có thể xuất hiện trong profiler không?
- Sau khi điều tra, cấu hình nào cần đưa về trạng thái ban đầu?

MongoDB **database profiler** là một công cụ hữu ích để phân tích workload query. Nhưng profiler không miễn phí: việc tạo và lưu hồ sơ cho một operation cũng cần xử lý, bộ nhớ, I/O và dung lượng lưu trữ.

Một cách điều tra thiếu kiểm soát có thể tạo ra vòng lặp xấu:

```text
Ứng dụng chậm
     │
     ▼
Bật profile mọi operation (level 2)
     │
     ▼
Số bản ghi system.profile tăng mạnh
     │
     ▼
CPU + writes + storage pressure tăng
     │
     ▼
Ứng dụng chậm thêm
     │
     ▼
Kết quả đo không còn phản ánh workload ban đầu
```

**Thông điệp chính:** Database profiler là **công cụ quan sát có chi phí**, không phải một công tắc debug nên bật tối đa. Hãy chọn đúng mức ghi nhận, ngưỡng, filter, thời lượng và phạm vi; kết hợp với diagnostic logs, metrics, Java Driver tracing và `explain()`.

### 1.1. Mục tiêu sau bài học

Bạn có thể:

1. Giải thích database profiler là gì và dữ liệu được ghi ở đâu.
2. Phân biệt profiling levels `0`, `1` và `2`.
3. Hiểu `slowms`, `sampleRate` và `filter`, bao gồm tác động có thể vượt database đang cấu hình.
4. Đọc các trường quan trọng trong `system.profile`.
5. Ước lượng chi phí ghi, storage, CPU và privacy khi tăng mức profiling.
6. Thực hành `db.getProfilingStatus()` và `db.setProfilingLevel()`.
7. Chọn filter/profiler đúng lúc thay vì thu thập toàn bộ queries.
8. Dùng `explain("executionStats")` để tìm nguyên nhân performance.
9. Phân biệt profiling records với diagnostic slow-operation logs.
10. Thiết kế runbook bật, giám sát, tắt và khôi phục profiler trên môi trường được phép.

---

## 2. Database profiler là gì?

**Database profiler** là cơ chế của MongoDB Server dùng để thu thập thông tin chi tiết về những database operations thỏa điều kiện profiling.

Trên `mongod`, các profile records được lưu vào collection đặc biệt:

```text
<database>.system.profile
```

Ví dụ:

```text
commerce.system.profile
analytics.system.profile
profile_lab.system.profile
```

Một record có thể chứa:

- Thời điểm operation.
- Loại thao tác: `query`, `command`, `getmore`, `update`, v.v.
- Namespace.
- Một phần hoặc toàn bộ command document theo khả năng ghi nhận và giới hạn.
- Tổng thời gian operation tính bằng milliseconds.
- Query plan summary.
- Index keys và documents đã xét.
- Số documents trả về.
- Lock/yield/storage hoặc execution details khi hỗ trợ.
- Cursor và query shape/plan identifiers tùy server version.

### 2.1. Profiler không phải database log file

So sánh:

```text
MongoDB server process
     │
     ├── Diagnostic log
     │     stdout / mongod.log / container collector
     │     INFO, WARNING, ERROR, DEBUG, Slow query
     │
     └── Database profiler
           <database>.system.profile
           các operation records được chọn
```

Diagnostic log ghi nhiều loại trạng thái server. Profiler tập trung vào operation profiling trong phạm vi database, lưu records dưới dạng documents trong MongoDB.

### 2.2. Profiler không phải APM toàn ứng dụng

Profiler nhìn những thao tác **đã đến MongoDB server**. Nó không tự đo toàn bộ:

- Thời gian HTTP request.
- Business logic trong Java.
- Thời gian chờ connection pool.
- Network giữa ứng dụng và MongoDB.
- Retries phía driver.
- Gọi API tới hệ thống khác.
- Render/serialize response.
- UI frontend latency.

Một API có p95 1.000 ms và profile record `millis: 80` không có nghĩa MongoDB gây ra toàn bộ 1.000 ms.

### 2.3. Profiler không thay cho backup/audit

Collection `system.profile` là dữ liệu quan sát có vòng đời giới hạn, không phải:

- Backup database.
- Audit trail đầy đủ cho bảo mật/compliance.
- Danh sách toàn bộ query từng chạy từ trước tới nay.
- Nhật ký giao dịch có khả năng replay.
- Tài liệu đảm bảo mọi request đã được capture.

Nếu cần kiểm toán truy cập, dùng database auditing features được triển khai đúng theo edition/plan và chính sách bảo mật.

---

## 3. Đặt profiler trong hệ thống observability

Một hệ thống sản xuất thường cần nhiều tín hiệu:

| Nguồn | Cung cấp | Phù hợp với |
|---|---|---|
| Database profiler | Chi tiết thao tác được chọn trên mongod | Điều tra query shape, plan, scan counts |
| Diagnostic slow-operation log | Thông tin slow operations trong server log | Theo dõi rộng, tập trung logs |
| `explain("executionStats")` | Kế hoạch và counters từ một truy vấn phân tích | Kiểm chứng scan/index/sort |
| `serverStatus` / metrics | Trạng thái connection, cache, operations, locks | Giám sát xu hướng và tải |
| `currentOp` | Operations đang chạy ở thời điểm gọi | Điều tra hoạt động hiện tại |
| Java Driver command monitoring | Command latency/success/failure từ client | Tách server/network/driver |
| Distributed tracing | Request spans qua các services | Correlation end-to-end |
| Atlas/managed monitoring | Metrics/profiler/logs theo tier | Quan sát cluster managed |

Không có nguồn nào thay thế hoàn toàn các nguồn khác.

### 3.1. Ví dụ phối hợp dữ liệu

Giả sử:

```text
HTTP p95 tăng từ 100 ms lên 900 ms
Driver command duration p95 ~700 ms
system.profile cho thấy:
  ns: shop.orders
  planSummary: COLLSCAN
  docsExamined: 450000
  nreturned: 10
  millis: 650
explain cho thấy index tenantId/status chưa phù hợp
```

Một giả thuyết hợp lý là MongoDB phải quét quá nhiều documents cho query. Tuy nhiên còn cần xác minh workload thực, index changes, resource contention và tác động sau khi sửa.

### 3.2. Không phải lúc nào cũng cần profiler

Nếu database đang chậm do disk đầy, replica set mất primary hoặc network outage, việc bật profiling level 2 khó có ích và còn thêm tải.

Nên bắt đầu từ câu hỏi điều tra và nguồn có khả năng trả lời với chi phí thấp nhất.

---

## 4. Ba profiling levels: 0, 1 và 2

MongoDB cung cấp ba mức profiling kinh điển:

| Level | Hành vi | Phù hợp |
|---|---|---|
| `0` | Tắt ghi database profiler records vào `system.profile` | Trạng thái vận hành bình thường nếu chưa cần profiling |
| `1` | Ghi những thao tác thỏa tiêu chí slow operation/filter | Điều tra có chọn lọc |
| `2` | Ghi các thao tác được profiler hỗ trợ, theo cấu hình áp dụng | Lab hoặc điều tra đặc biệt ngắn |

### 4.1. Level 0 — Profiler tắt

```javascript
db.setProfilingLevel(0);
```

Không ghi operation profiles mới vào `system.profile` theo cơ chế profiler thông thường.

**Nhưng diagnostic log của MongoDB vẫn có thể ghi các slow operations.** Tắt profiler không đồng nghĩa tắt slow query log.

### 4.2. Level 1 — Thu thập operations thỏa điều kiện

```javascript
db.setProfilingLevel(1, {
  slowms: 100,
  sampleRate: 1.0
});
```

Minh họa:

- Profiling level 1.
- Slow threshold 100 ms.
- Sampling rate 1.0 (toàn bộ operations được chọn theo logic sampling/threshold, không phải tất cả database operations).

Trên deployment phù hợp, đây thường là lựa chọn tốt để bắt đầu điều tra.

### 4.3. Level 2 — Thu thập rộng

```javascript
db.setProfilingLevel(2);
```

Ở level 2, profiler ghi gần như tất cả operations thuộc phạm vi có thể profile, thay vì chỉ những thao tác chậm theo threshold.

Nguy cơ:

- Tạo rất nhiều profile documents.
- Gây writes bổ sung.
- Tăng CPU và I/O.
- Kích hoạt thêm sự cạnh tranh tài nguyên.
- Làm đầy vòng đệm capped collection nhanh.
- Dễ ghi thông tin nhạy cảm hơn.
- Làm sai lệch benchmark và p99 latency.

**Không bật level 2 lâu dài trên production.** Nếu cần thu thập toàn bộ trong một lab cô lập, đặt thời lượng ngắn và quan sát overhead.

### 4.4. So sánh một workload

Giả sử có 10.000 operations/giây và 5% vượt ngưỡng 100 ms.

- Level 0: không ghi hồ sơ vào `system.profile`, nhưng slow-operation diagnostic logs có thể vẫn phát sinh.
- Level 1, slowms 100 ms, sampleRate 1: số ứng viên profile khoảng 500 operations/giây nếu phân bố và logic sampling như mô hình đơn giản.
- Level 1, sampleRate 0.1: khoảng 50 bản ghi/giây trong ví dụ lý tưởng.
- Level 2: có thể tiến gần 10.000 profile records/giây nếu mọi operation thuộc loại được profile, lớn hơn rất nhiều.

Con số mang tính minh họa, **không phải cam kết số record chính xác**; các operations, filters và internal exclusions ảnh hưởng kết quả thực.

---

## 5. Collection system.profile hoạt động như thế nào?

MongoDB lưu các profiler records trong collection:

```javascript
db.getSiblingDB("profile_lab").system.profile
```

Đây là một **capped collection** do MongoDB quản lý cho mục tiêu profiling.

### 5.1. Capped collection nghĩa là gì?

Capped collection có kích thước giới hạn; khi chạm giới hạn, dữ liệu cũ có thể bị thay thế bởi records mới theo cơ chế của capped storage.

Hệ quả:

- `system.profile` không phải kho lịch sử vô hạn.
- Level 2 hoặc high-throughput level 1 có thể làm dữ liệu cũ biến mất rất nhanh.
- Những events hiếm có thể bị overwrite trước khi người vận hành đọc.
- Cần trích xuất/summarize vào hệ quan sát phù hợp nếu cần lưu dài hạn.
- Không tăng dung lượng profiler bừa bãi chỉ để tránh mất records; làm vậy có thể tăng disk/operational overhead.

### 5.2. system.profile thuộc database nào?

Nếu profiler đang bật trên `profile_lab`, records tương ứng nằm trong:

```text
profile_lab.system.profile
```

Không mặc định tìm mọi profile records của `commerce` trong `admin.system.profile`.

### 5.3. Có phải toàn bộ operations đều được ghi?

Không nên khẳng định “mọi lệnh” được ghi tuyệt đối. Profiler có phạm vi hỗ trợ, điều kiện level/filter, quyền, server version, và một số hoạt động nội bộ có thể không được profile như thao tác ứng dụng thông thường.

Đặc biệt, đọc chính `system.profile` không nên được kỳ vọng tạo ra một vòng lặp tự ghi hồ sơ không ngừng.

### 5.4. Quyền truy cập

Đọc profiler có thể yêu cầu privileges thích hợp đối với `system.profile`. User chỉ biết kết nối tới database không tự có quyền quản trị profiling.

Các thao tác như bật/tắt profiler, chỉnh global slow thresholds hoặc log settings cần quyền quản trị phù hợp.

Trong production:

- Tách principal đọc telemetry khỏi principal chỉnh profiling.
- Không cấp `root` cho ứng dụng chỉ để có profiler.
- Kiểm soát truy cập records có thể chứa query values/PII.

### 5.5. Dung lượng collection và thời gian giữ dữ liệu

Không thể tính thời gian retention chỉ từ giới hạn size, vì event size và event rate thay đổi theo workload.

Ví dụ:

```text
system.profile capped capacity: 100 MiB (ví dụ)
Trung bình record:             2 KiB
Khả năng chứa lý thuyết:      khoảng 51.200 records
Tốc độ profile:               500 records/giây
Thời gian lưu lý thuyết:      khoảng 102 giây
```

Đây là tính toán mô hình. Thực tế còn phụ thuộc storage overhead, kích thước documents không đồng đều và hành vi capped collection.

**Bài học:** 100 MiB profiler có thể chỉ giữ vài phút khi log rate cao.

---

## 6. Cấu hình profiler bằng mongosh

### 6.1. Xem cấu hình hiện tại

Trước khi thay đổi bất kỳ giá trị nào:

```javascript
const lab = db.getSiblingDB("profile_lab");

printjson(lab.getProfilingStatus());
print("Current level:", lab.getProfilingLevel());
```

Một kết quả ví dụ:

```json
{
  "was": 0,
  "slowms": 100,
  "sampleRate": 1,
  "ok": 1
}
```

Ý nghĩa:

- `was`: profiling level tại thời điểm truy vấn.
- `slowms`: ngưỡng đang sử dụng.
- `sampleRate`: tỉ lệ sampling.
- Các fields khác có thể xuất hiện ở một số version/cấu hình.

### 6.2. Lưu trạng thái ban đầu

Trong một phiên `mongosh` lab:

```javascript
const profileDb = db.getSiblingDB("profile_lab");
const originalProfiling = profileDb.getProfilingStatus();

printjson(originalProfiling);
```

Nếu dự kiến thay đổi trên hệ thống thực, ghi status vào change record **có kiểm soát truy cập**, và ghi thời điểm, owner, phiên bản server.

### 6.3. Bật level 1

```javascript
profileDb.setProfilingLevel(1, {
  slowms: 100,
  sampleRate: 1.0
});

printjson(profileDb.getProfilingStatus());
```

Trước khi gọi, phải có quyền quản trị tương ứng. Một số deployment managed không cho phép dùng API này trực tiếp.

### 6.4. Đổi sampling

```javascript
profileDb.setProfilingLevel(1, {
  slowms: 100,
  sampleRate: 0.25
});
```

Tỷ lệ 0.25 nghĩa là sampling khoảng một phần tư các thao tác thuộc điều kiện, theo semantics của phiên bản; không bảo đảm có đúng một record trong mỗi bốn thao tác.

### 6.5. Tắt profiler

```javascript
profileDb.setProfilingLevel(0);
```

**Chỉ chạy thế này chưa chắc đã rollback đầy đủ.** Nếu đã thay đổi `slowms` hoặc `sampleRate`, những giá trị đó có thể vẫn khác trạng thái ban đầu. Phải khôi phục theo saved configuration và chú ý filter.

### 6.6. Khôi phục đúng trạng thái ban đầu

Một runbook cần:

1. Lưu `was`/level ban đầu.
2. Lưu `slowms`.
3. Lưu `sampleRate`.
4. Lưu `filter` nếu có.
5. Lưu sự khác biệt giữa explicit và inherited config nếu API/triển khai hỗ trợ.
6. Đối chiếu tác động global.
7. Khôi phục bằng lệnh tương thích với phiên bản.
8. Đọc lại status và xác nhận.

Ví dụ *chỉ khi trạng thái ban đầu đúng là level 0, slowms 100, sampleRate 1 và không có filter*:

```javascript
profileDb.setProfilingLevel(0, {
  slowms: 100,
  sampleRate: 1.0
});

printjson(profileDb.getProfilingStatus());
```

Không sử dụng mặc định của ví dụ để thay thế trạng thái production không biết rõ.

---

## 7. Điểm quan trọng: slowms và sampleRate có thể mang phạm vi rộng

Một nhầm lẫn phổ biến là nghĩ:

> “Mình gọi `db.getSiblingDB("profile_lab").setProfilingLevel(1, {slowms: 10})` thì chỉ các lệnh của database này mới dùng threshold 10 ms.”

Trên MongoDB `mongod`, **profiling level là cấu hình theo database**, trong khi các tham số như `slowms` và `sampleRate` được sử dụng ở mức process/global theo những hành vi tài liệu MongoDB quy định.

Vì vậy, đặt threshold nhỏ từ một database có thể ảnh hưởng **slow-operation diagnostic logging ở các database khác** trên cùng process.

### 7.1. Phân biệt hai phạm vi

```text
mongod process
│
├── Database A
│     profiler level: 0/1/2
│
├── Database B
│     profiler level: 0/1/2
│
└── Slow-operation threshold / sampling settings
      có tác động rộng theo server configuration
```

Không coi việc gọi helper trên `profile_lab` là bảo đảm “không chạm workloads khác”.

### 7.2. Vì sao gây sự cố?

Nếu 10 ứng dụng dùng chung một `mongod` process:

- Developer bật profiling level 1 trên database test.
- Đồng thời đặt `slowms: 1`.
- Lưu lượng production trên database khác vẫn có thể phát sinh nhiều diagnostic slow logs do threshold chung.
- Log collector/disk bị quá tải dù profiler chỉ bật trên database test.

### 7.3. Runbook phải ghi phạm vi tác động

Trước khi thay đổi:

- Kiểm tra phiên bản MongoDB.
- Xem config effective của process.
- Xác định các databases/workloads cùng process.
- Ước lượng volume theo peak operations/s.
- Chọn cửa sổ ngắn.
- Có người chịu trách nhiệm khôi phục.
- Theo dõi bytes/s và disk free.

---

## 8. Hiểu slowms: ngưỡng “chậm” không giống SLA của ứng dụng

Tham số `slowms`, thường được cấu hình tương đương `slowOpThresholdMs`, là ngưỡng MongoDB dùng để phân loại các thao tác là chậm trong những cơ chế profiling/diagnostic logging hỗ trợ.

### 8.1. Default thường gặp

Trong nhiều bản MongoDB Server, ngưỡng mặc định thường là 100 ms. Nhưng **không mặc định production thực tế đang giữ default**; luôn đọc `getProfilingStatus()` hoặc config.

### 8.2. Server timing và client timing khác nhau

Giả sử:

```text
HTTP request latency:         950 ms
Driver command latency:       650 ms
MongoDB profiler millis:      480 ms
Network / scheduling / khác:  phần còn lại
```

Các con số chỉ minh họa, nhưng cho thấy profiler không đo toàn bộ request.

### 8.3. SLO khác nhau theo workload

| Workload | Mục tiêu ví dụ | Ngưỡng profiler cần cân nhắc |
|---|---|---|
| Online checkout | p95 dưới 150 ms | Có thể cần quan sát commands dưới 100 ms |
| Batch analytics | Thời gian dưới 60 s | 100 ms có thể thu quá nhiều dữ liệu |
| Backoffice report | p95 dưới 3 s | Chọn threshold theo query/operation type |
| Streaming consumer | Lag và throughput | Theo dõi getMore, writes, batches |
| Multi-tenant API | SLO khác theo nhóm tenant | Tập trung shape, rate và tenant skew |

Mục đích không phải đặt một threshold chuẩn cho mọi workload. Đặt threshold sao cho thu thập **đủ tín hiệu** mà không gây log storm.

### 8.4. Threshold cao có thể bỏ lỡ query lặp thường xuyên

Giả sử mỗi lần query tốn 80 ms và lặp 1.000 lần/giây. Nó không vượt ngưỡng 100 ms nhưng chiếm nhiều CPU và làm tăng tổng tải hệ thống.

Đừng chỉ nhìn những slow queries vượt 100 ms; metrics CPU/ops, command latency histograms và application traces vẫn cần thiết.

### 8.5. Threshold cực thấp

```javascript
profileDb.setProfilingLevel(1, {
  slowms: 0,
  sampleRate: 1.0
});
```

Có thể tạo một lượng profile/slow log rất lớn theo điều kiện hỗ trợ. Chỉ dùng trong lab cô lập hoặc một cửa sổ điều tra được kiểm soát rất chặt.

Không coi đây là cấu hình lâu dài an toàn.

---

## 9. Hiểu sampleRate: giảm lượng thu thập không đồng nghĩa giảm tải truy vấn

`sampleRate` thường nằm trong khoảng từ 0.0 tới 1.0.

Ví dụ:

```javascript
profileDb.setProfilingLevel(1, {
  slowms: 100,
  sampleRate: 0.10
});
```

Ý nghĩa thực hành: thu thập một phần các operations đủ điều kiện theo sampling mechanism.

### 9.1. Vì sao cần sampling?

Nếu workload tạo 5.000 slow operations mỗi phút, ghi hết có thể gây:

- Lượng profile records lớn.
- Tốc độ overwrite capped collection cao.
- Chi phí đọc/ghi.
- Data export/ingest lớn.
- Rủi ro lưu nhiều query values nhạy cảm.

Sampling có thể làm điều tra nhẹ hơn mà vẫn nhìn thấy các pattern phổ biến.

### 9.2. Sampling không đảm bảo ghi đúng tỉ lệ trên từng nhóm nhỏ

Với một query shape xuất hiện ba lần, sampleRate 0.1 hoàn toàn có thể không ghi bản nào. Vì vậy:

- Không lấy “không có profile record” để kết luận không có truy vấn chậm.
- Không dùng sampling profiler làm audit trail chính xác.
- Khi phân tích rare incidents, có thể cần phạm vi lọc khác.
- Khi ước lượng total events từ sampled data phải báo rõ uncertainty.

### 9.3. Không so log counts qua hai lần đổi sampleRate

Giả sử:

```text
Trước thay đổi:
sampleRate = 1.0
profile records = 1.000/phút

Sau thay đổi:
sampleRate = 0.1
profile records = 100/phút
```

Không thể kết luận workload đã cải thiện 10 lần. Có thể chỉ do thu thập ít hơn.

### 9.4. Sampling vẫn có chi phí

Sampling không có nghĩa “0 overhead”. Server vẫn phải:

- Xác định operation đủ điều kiện.
- Lựa chọn record cần lưu.
- Tạo document cho operations được chọn.
- Ghi vào `system.profile`.
- Có thể serialize các trường dữ liệu chi tiết.

Sampling giảm chi phí nhưng không xóa hoàn toàn overhead.

### 9.5. Khi nào sampleRate nhỏ hữu ích?

- Workload có hàng triệu operations.
- Mục tiêu là xác định **query shapes thường gặp**.
- Incident đủ dài để có nhiều mẫu.
- Có metrics latency liên tục để đối chiếu.
- Không yêu cầu ghi từng slow operation.

---

## 10. Profiling filter: chọn tín hiệu theo điều kiện

Một số MongoDB Server releases hỗ trợ **profiling filter** để chỉ thu thập operations phù hợp điều kiện.

Ví dụ hướng thiết kế:

> “Tôi chỉ muốn biết các thao tác vào collection `orders`, không cần profile tất cả collection trong database.”

### 10.1. Ví dụ filter theo namespace

Trong MongoDB version hỗ trợ filter:

```javascript
const profileDb = db.getSiblingDB("profile_lab");

profileDb.setProfilingLevel(1, {
  filter: {
    ns: "profile_lab.orders"
  }
});
```

Sau đó:

```javascript
printjson(profileDb.getProfilingStatus());
```

Lưu ý: Filter sử dụng các trường được MongoDB hỗ trợ trong cấu trúc operation/profiling, và semantics có thể khác theo version. Cần đọc documentation của server đang chạy trước khi áp dụng vào production.

### 10.2. Filter có thể thay đổi vai trò của slowms/sampleRate

**Đặc biệt quan trọng:** Khi có profiling filter, MongoDB documentation mô tả rằng cấu hình `slowms` và `sampleRate` có thể **không còn được dùng cho profiler và diagnostic slow logging theo cách threshold thông thường**; filter có thể quyết định trực tiếp những operations được ghi.

Do đó không nên viết:

```javascript
profileDb.setProfilingLevel(1, {
  slowms: 100,
  sampleRate: 0.01,
  filter: { ns: "profile_lab.orders" }
});
```

rồi tin rằng filter chọn orders **và** sampleRate luôn giới hạn còn 1% các thao tác trên 100 ms. Hãy kiểm tra rõ interaction của options trong tài liệu phiên bản và trạng thái effective.

### 10.3. Filter theo thời gian và cost

Một filter không cẩn thận có thể chọn quá nhiều events. Ví dụ chỉ lọc theo namespace có throughput rất lớn sẽ vẫn tạo áp lực đáng kể.

Tốt hơn là:

1. Ước lượng operations/s cho namespace.
2. Chọn filter thật hẹp nếu có hỗ trợ.
3. Đặt cửa sổ điều tra ngắn.
4. Quan sát rate thực tế của profile records.
5. Khôi phục filter sau khi xong.

### 10.4. Filter không thay thế profiler level

Filter quyết định selection; level quyết định phạm vi profiling theo cơ chế server. Đừng cho rằng đặt filter nhưng level 0 sẽ ghi ra đầy đủ `system.profile`.

### 10.5. Xóa filter đúng cách

Khi khôi phục, cần xử lý cả filter cũ. Một số APIs và versions cho phép đặt `filter: "unset"` theo tài liệu.

Không ngẫu nhiên xóa filter trên production nếu nó được cấu hình có chủ đích cho một monitoring workflow khác. Lưu và khôi phục state đầy đủ.

### 10.6. Nên dùng filter hay giảm threshold?

| Mục đích | Hướng ưu tiên |
|---|---|
| Tìm mọi slow operations trên mongod | Threshold + sampling/logs |
| Chỉ quan tâm collection cụ thể | Filter khi version hỗ trợ |
| Điều tra một query shape | Filter/query telemetry + explain |
| Cần phân tích P99 latency toàn ứng dụng | APM/metrics; profiler là bằng chứng bổ sung |
| Cần ghi chính xác từng thao tác bảo mật | Auditing được hỗ trợ, không profiler |

---

## 11. Cấu hình trong mongod.conf

Trên self-managed deployment, MongoDB có nhóm cấu hình `operationProfiling`:

```yaml
operationProfiling:
  mode: off
  slowOpThresholdMs: 100
  slowOpSampleRate: 1.0
```

### 11.1. Ý nghĩa các fields

| Config | Ý nghĩa |
|---|---|
| `mode: off` | Tắt database profiling |
| `mode: slowOp` | Profile slow operations theo cấu hình |
| `mode: all` | Profile rộng các operations thuộc phạm vi |
| `slowOpThresholdMs` | Ngưỡng thời gian tính ms |
| `slowOpSampleRate` | Sampling rate |

Một số phiên bản cung cấp `filter` trong cấu hình/hệ lệnh điều khiển; dùng đúng syntax theo version.

### 11.2. Sự khác nhau giữa cấu hình startup và thay đổi runtime

- `mongod.conf` thường dùng lúc khởi động service.
- `db.setProfilingLevel()` thay đổi trạng thái runtime ở database/server theo semantics hỗ trợ.
- Runtime values không nhất thiết được persist vào file config.
- Restart có thể đưa cấu hình trở về những giá trị startup nếu không có automation đồng bộ.

Vì vậy khi troubleshooting sau restart, phải xác minh effective settings thay vì suy ra từ ticket thay đổi đã thực hiện tuần trước.

### 11.3. Diagnostic logging là luồng khác

Có thể cấu hình:

```yaml
systemLog:
  destination: file
  path: /var/log/mongodb/mongod.log
  logAppend: true
  verbosity: 0
```

Ở đây `verbosity: 0` không tắt mọi message và **không có nghĩa slow operation logs chắc chắn tắt**.

Không nhầm:

```text
operationProfiling.mode
    ↔ profile documents trong system.profile

systemLog.verbosity
    ↔ mức chi tiết diagnostic messages
```

### 11.4. Managed deployments

Atlas và các nhà cung cấp MongoDB managed có thể hạn chế thao tác chỉnh profiler/config, hoặc cung cấp Query Profiler/Performance Advisor/metrics riêng.

Không cho rằng có quyền kết nối database tức là được phép sửa `mongod.conf` hoặc đặt level 2 trên Atlas.

---

## 12. Bài thực hành: tạo database và dữ liệu

Trong `mongosh` kết nối một **lab MongoDB mongod** được phép thay đổi profiling.

### 12.1. Chuẩn bị collection

```javascript
const lab = db.getSiblingDB("profile_lab");
const orders = lab.getCollection("orders");

orders.insertMany([
  {
    _id: 1, tenantId: "t1", customerId: "C01",
    status: "PENDING", total: NumberDecimal("120.00"),
    createdAt: ISODate("2026-11-01T08:00:00Z")
  },
  {
    _id: 2, tenantId: "t1", customerId: "C02",
    status: "PAID", total: NumberDecimal("550.00"),
    createdAt: ISODate("2026-11-01T09:00:00Z")
  },
  {
    _id: 3, tenantId: "t1", customerId: "C01",
    status: "PENDING", total: NumberDecimal("89.00"),
    createdAt: ISODate("2026-11-02T08:00:00Z")
  },
  {
    _id: 4, tenantId: "t1", customerId: "C03",
    status: "PAID", total: NumberDecimal("220.00"),
    createdAt: ISODate("2026-11-02T09:00:00Z")
  },
  {
    _id: 5, tenantId: "t1", customerId: "C04",
    status: "CANCELLED", total: NumberDecimal("90.00"),
    createdAt: ISODate("2026-11-03T08:00:00Z")
  },
  {
    _id: 6, tenantId: "t2", customerId: "C10",
    status: "PENDING", total: NumberDecimal("75.00"),
    createdAt: ISODate("2026-11-03T09:00:00Z")
  },
  {
    _id: 7, tenantId: "t2", customerId: "C10",
    status: "PAID", total: NumberDecimal("425.00"),
    createdAt: ISODate("2026-11-04T08:00:00Z")
  },
  {
    _id: 8, tenantId: "t1", customerId: "C02",
    status: "PENDING", total: NumberDecimal("150.00"),
    createdAt: ISODate("2026-11-04T09:00:00Z")
  },
  {
    _id: 9, tenantId: "t2", customerId: "C11",
    status: "PAID", total: NumberDecimal("199.00"),
    createdAt: ISODate("2026-11-05T08:00:00Z")
  },
  {
    _id: 10, tenantId: "t1", customerId: "C01",
    status: "PAID", total: NumberDecimal("330.00"),
    createdAt: ISODate("2026-11-05T09:00:00Z")
  },
  {
    _id: 11, tenantId: "t2", customerId: "C12",
    status: "PENDING", total: NumberDecimal("610.00"),
    createdAt: ISODate("2026-11-06T08:00:00Z")
  },
  {
    _id: 12, tenantId: "t1", customerId: "C05",
    status: "PENDING", total: NumberDecimal("410.00"),
    createdAt: ISODate("2026-11-06T09:00:00Z")
  }
]);

print("Count:", orders.countDocuments({}));
```

Đây là **12 documents**, sử dụng một database lab trống. Nếu chạy hai lần, các `_id` trùng gây duplicate key error.

### 12.2. Truy vấn thường gặp

```javascript
printjson(orders.find({
  tenantId: "t1",
  status: "PENDING"
}).toArray());

printjson(orders.find({
  customerId: "C01"
}).sort({ createdAt: -1 }).toArray());

printjson(orders.aggregate([
  { $match: { status: "PAID" } },
  {
    $group: {
      _id: "$tenantId",
      revenue: { $sum: "$total" },
      count: { $sum: 1 }
    }
  }
]).toArray());
```

### 12.3. Tạo index đối chứng

```javascript
orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "idx_tenant_status_time" }
);

orders.createIndex(
  { customerId: 1, createdAt: -1 },
  { name: "idx_customer_time" }
);

printjson(orders.getIndexes());
```

Bài lab nhỏ không có đủ dữ liệu để so sánh benchmark latency hoặc chứng minh planner phải dùng IXSCAN.

---

## 13. Bật profiler trong lab và đọc records

### 13.1. Snapshot trạng thái ban đầu

```javascript
const profileDb = db.getSiblingDB("profile_lab");
const before = profileDb.getProfilingStatus();

printjson(before);
```

Nếu lab mới chưa có profiler, có thể thấy level 0.

### 13.2. Bật profile với threshold

```javascript
profileDb.setProfilingLevel(1, {
  slowms: 50,
  sampleRate: 1.0
});
```

Chạy lại các queries ở mục trước.

### 13.3. Đọc system.profile

```javascript
profileDb.system.profile
  .find({
    ns: "profile_lab.orders"
  })
  .sort({ ts: -1 })
  .limit(10)
  .pretty();
```

Với 12 documents, queries thường không vượt 50 ms nên có thể **không có record nào**.

Không coi đó là lỗi MongoDB; có thể threshold/sampling không chọn query.

### 13.4. Tùy chọn lab: level 2 ngắn hạn

Nếu lab cô lập, traffic thấp, được phép bật profiling:

```javascript
profileDb.setProfilingLevel(2);
```

Chạy 1–2 queries nhỏ rồi đọc:

```javascript
profileDb.system.profile
  .find({
    ns: "profile_lab.orders"
  })
  .sort({ ts: -1 })
  .limit(5)
  .pretty();
```

Sau đó **khôi phục ngay** mức ban đầu và parameters phù hợp.

### 13.5. Ví dụ record rút gọn

Một profiler record **minh họa**, không phải schema cố định:

```javascript
{
  op: "query",
  ns: "profile_lab.orders",
  command: {
    find: "orders",
    filter: {
      tenantId: "t1",
      status: "PENDING"
    },
    "$db": "profile_lab"
  },
  keysExamined: 5,
  docsExamined: 5,
  nreturned: 4,
  millis: 2,
  planSummary: "IXSCAN { tenantId: 1, status: 1, createdAt: -1 }",
  ts: ISODate("2026-11-14T08:30:00Z")
}
```

Các fields như `keysExamined`/`docsExamined`/`planSummary` tùy operation/server version, và planner có thể chọn `COLLSCAN` trên tập nhỏ.

---

## 14. Truy vấn system.profile đúng cách

### 14.1. Records gần nhất

```javascript
const p = db.getSiblingDB("profile_lab");

p.system.profile.find(
  {},
  {
    ts: 1,
    op: 1,
    ns: 1,
    millis: 1,
    planSummary: 1
  }
).sort({ ts: -1 }).limit(20);
```

Projection tránh vô tình in toàn bộ command payload chứa thông tin khách hàng.

### 14.2. Lọc duration

```javascript
p.system.profile.find(
  {
    ns: "profile_lab.orders",
    millis: { $gte: 50 }
  },
  {
    ts: 1,
    op: 1,
    ns: 1,
    millis: 1,
    keysExamined: 1,
    docsExamined: 1,
    nreturned: 1,
    planSummary: 1
  }
).sort({ ts: -1 }).limit(20);
```

Nếu profiler đã được bật với threshold thấp hơn hoặc level 2, filter `millis >= 50` chọn records cần xem.

### 14.3. Phân tích theo namespace

```javascript
p.system.profile.aggregate([
  {
    $match: {
      ns: /^profile_lab[.]/
    }
  },
  {
    $group: {
      _id: "$ns",
      records: { $sum: 1 },
      maxMillis: { $max: "$millis" },
      avgMillis: { $avg: "$millis" }
    }
  },
  {
    $sort: {
      maxMillis: -1
    }
  },
  { $limit: 10 }
]);
```

Những số liệu này áp dụng **chỉ cho records còn lưu và được profiler chọn**. Không báo cáo `avgMillis` từ một sample như latency trung bình chính xác của mọi query nếu sampling/filter có bias.

### 14.4. Top records theo duration

```javascript
p.system.profile
  .find(
    { millis: { $exists: true } },
    {
      ts: 1,
      ns: 1,
      op: 1,
      millis: 1,
      planSummary: 1,
      keysExamined: 1,
      docsExamined: 1,
      nreturned: 1
    }
  )
  .sort({ millis: -1 })
  .limit(10);
```

Đây là phân tích “top chậm nhất trong những records đã thu được”, không phải top chậm nhất trong lịch sử cluster.

### 14.5. Query system.profile có overhead không?

Có. Đọc/aggregate chính collection này vẫn tốn tài nguyên MongoDB, dù nó là capped collection.

Không để dashboard chạy aggregation quét profiler hàng giây trên một instance đang chịu áp lực.

Nếu cần phân tích liên tục, xem khả năng xuất/ingest vào hệ thống logs/metrics được tối ưu cho time-series analysis và có RBAC/redaction.

---

## 15. Các fields quan trọng của profiler record

| Field | Ý nghĩa | Cách dùng |
|---|---|---|
| `ts` | Timestamp | Timeline/correlation |
| `op` | Loại operation | Phân biệt query, getmore, update, command |
| `ns` | Namespace | Tìm collection chịu ảnh hưởng |
| `command` | Command document | Query shape/filter/sort, nhạy cảm |
| `millis` | Thời gian operation trên server | Xếp hạng/so với threshold |
| `planSummary` | Tóm tắt plan | Nhận diện COLLSCAN/IXSCAN |
| `keysExamined` | Index keys đã xét | Đánh giá phạm vi scan |
| `docsExamined` | Documents đã xét | Đánh giá filter selectivity |
| `nreturned` | Documents trả về | Đối chiếu scan ratio |
| `numYield` | Lần yield (khi có) | Tham khảo concurrency |
| `locks` | Lock information (khi có) | Điều tra contention |
| `responseLength` | Kích thước response (khi có) | Theo dõi payload lớn |
| `cursorid` | Cursor identifier (khi có) | Phân tích getMore |
| `usedDisk` | Có dùng disk trong một số execution | Điều tra sort/group spilling |
| `errCode`/`errMsg` | Thông tin lỗi (khi có) | Phân loại thất bại |
| Query/plan identifiers | Gom những execution cùng shape/plan | Theo dõi version-specific fields |

Không coi bảng này là schema bắt buộc của mọi record. Ví dụ `nreturned` không áp dụng giống nhau cho mọi write command, một số fields chỉ xuất hiện trên engine/version phù hợp.

### 15.1. Duration khác end-to-end latency

`millis` là server-side timing được ghi trong profile. User-facing response time còn có:

- Connection pool checkout.
- Driver server selection.
- Network/TLS.
- BSON serialization/deserialization.
- Multiple cursor batches.
- Retries.
- Logic ứng dụng.

### 15.2. keysExamined cao

Một query có `IXSCAN` nhưng `keysExamined=400000` có thể vẫn đắt, đặc biệt nếu `nreturned=10`.

**IXSCAN có nghĩa dùng index, không có nghĩa index bounds đã đủ hẹp.**

### 15.3. docsExamined cao

Ví dụ:

```text
docsExamined = 300000
nreturned    = 12
planSummary  = COLLSCAN
```

Đây là dấu hiệu hữu ích để xem index/filter, nhưng không tự chứng minh “thiếu index là nguyên nhân duy nhất”. Query analytics cố ý scan toàn tập có thể hợp lý.

### 15.4. usedDisk

Một số pipeline aggregation/sort có thể dùng disk để xử lý intermediate data, tùy operators/version/settings. Nếu `usedDisk` xuất hiện, cần đối chiếu:

- Pipeline stages.
- Index cho sort/group.
- Cardinality.
- Memory/disk pressure.
- MongoDB Server version và allowDiskUse semantics.

Không tự thêm `allowDiskUse:true` rồi coi đó là tối ưu vĩnh viễn.

### 15.5. Query identifiers thay đổi theo version

Một số MongoDB versions có `queryHash`, `planCacheKey` và các tên mới như `planCacheShapeHash`/`queryShapeHash` trong những context nhất định.

Không hardcode dashboard vào duy nhất một tên field mà chưa kiểm tra MongoDB Server version. Cần canonicalize theo release.

---

## 16. Scan ratio: đọc đúng, tránh kết luận máy móc

Một chỉ số tham khảo:

\[
\text{scan ratio} = \frac{\text{docsExamined}}{\max(\text{nreturned},1)}
\]

Ví dụ:

```text
docsExamined = 100000
nreturned    = 10

scan ratio   = 10000
```

Nó gợi ý server phải xét rất nhiều documents cho một kết quả nhỏ.

### 16.1. Khi scan ratio cao đáng chú ý

- API read có filter chọn lọc.
- Query theo tenant/customer/status.
- Query trả vài documents nhưng quét hàng trăm nghìn.
- API phân trang nhưng skip rất lớn.
- Index không phù hợp filter/sort.

### 16.2. Khi scan ratio cao lại hợp lý

- Aggregation `$group` toàn dataset.
- `countDocuments({})` trên một tập lớn tùy plan.
- Analytics/reporting cố ý quét nhiều documents.
- Query tính tổng và trả một document.

Không áp dụng một threshold scan ratio toàn cluster cho mọi operation type.

### 16.3. keysExamined / docsExamined / nreturned

Một số pattern:

| Pattern | Gợi ý |
|---|---|
| Keys 0, docs rất cao, returned thấp | Collection scan cần điều tra |
| Keys rất cao, docs cao, returned thấp | Index thiếu chọn lọc/range rộng |
| Keys rất cao, docs 0, returned thấp | Có thể covered index scan nhưng range vẫn rộng |
| Docs thấp, returned thấp, millis cao | Có thể chờ tài nguyên/lock/network hoặc workload khác |
| Returned rất cao | API không limit/projection hoặc nghiệp vụ phải tải nhiều dữ liệu |

Kết luận cần thêm query shape, explain, metrics và hành vi ứng dụng.

---

## 17. Profiler và explain: kết hợp để tìm nguyên nhân

Profiler cho thấy **một operation đã chạy** trong workload thật. `explain("executionStats")` giúp phân tích kế hoạch/query ở thời điểm kiểm tra.

Ví dụ:

```javascript
const lab = db.getSiblingDB("profile_lab");

const plan = lab.orders.find({
  tenantId: "t1",
  status: "PENDING"
}).sort({
  createdAt: -1
}).explain("executionStats");

printjson(plan.queryPlanner);
printjson(plan.executionStats);
```

### 17.1. So sánh

| Profiler | Explain | Lưu ý |
|---|---|---|
| `planSummary` | `winningPlan` | Explain chi tiết hơn |
| `docsExamined` | `totalDocsExamined` | Hai lần chạy có thể khác |
| `keysExamined` | `totalKeysExamined` | Có thể chịu ảnh hưởng selectivity |
| `nreturned` | `nReturned` | Cần cùng filter/sort/limit |
| `millis` | `executionTimeMillis` | Không phải một phép đo tuyệt đối giống nhau |
| `command` | Query input | Profiler có thể redacted/truncated |

### 17.2. Vì sao kết quả không khớp?

- Index đã thay đổi giữa hai lần chạy.
- Dữ liệu tăng/giảm.
- Query parameters có độ chọn lọc khác.
- Plan cache thay đổi.
- Replica set target khác.
- Load/CPU/cache khác.
- Profiler ghi một `getMore` còn explain khảo sát `find`.
- Query trong production có collation/hint/limit khác.
- Server engine/version khác.

**Không nói rằng explain chạy sau sự cố chắc chắn là plan đã chạy trong sự cố**.

### 17.3. Query ghi: không tái chạy để phân tích

Nếu profiler ghi:

```javascript
db.orders.deleteMany({ status: "EXPIRED" });
```

đừng copy thao tác đó rồi chạy lại trên production chỉ để xem performance. Nó có tác dụng phá hủy dữ liệu.

Dùng cách xem plan không thực thi phù hợp phiên bản, snapshot/staging, hoặc tool chuyên dụng an toàn.

---

## 18. Profiler và slow-operation diagnostic log: quan hệ đúng

Đây là một bẫy vận hành thường gặp.

### 18.1. Diagnostic slow logs có thể tồn tại khi profiler level 0

```text
Database profiler:
  level = 0
  system.profile: không ghi record mới

MongoDB diagnostic log:
  vẫn có thể có event "Slow query"
  dựa trên slow-operation settings
```

Vì vậy một DBA có thể xem server log thấy `Slow query` trong khi `system.profile` trống. Điều đó không nhất thiết là cấu hình sai.

### 18.2. Profiler level 1 không phải log file riêng

Khi bật level 1, records được lưu trong `system.profile` của database mongod. Server diagnostic log có thể đồng thời có slow entries liên quan.

Không đếm cả hai nguồn như hai operations khác nhau khi tổng hợp workload.

### 18.3. Dùng mức nào để theo dõi liên tục?

Thông thường:

- Diagnostic logs và metrics để quan sát liên tục.
- Profiler level 1 nếu có policy/workload phù hợp và overhead chấp nhận được.
- Profiler level 2 trong lab hoặc incident window đặc biệt ngắn.
- Structured log collector để phân tích trên nhiều nodes.
- Managed monitoring khi hạ tầng cung cấp.

Không có một cấu hình duy nhất phù hợp mọi SLA.

### 18.4. Log records có thể được truncate/redact

Server có thể giới hạn nội dung command trong logs, và profile records cũng cần kiểm tra trường nhạy cảm/truncation theo version.

Không dựa vào việc profiler luôn giữ toàn bộ giá trị query để replay hoặc audit.

---

## 19. Mongod và mongos: phạm vi quan sát

### 19.1. Profiler chạy trên mongod

Database profiler ghi vào `system.profile` trong database trên `mongod`.

### 19.2. Mongos không lưu profiler theo cách tương tự

`mongos` là router trong sharded cluster, không có local database profiler collection giống `mongod` để đọc mọi thao tác.

Vì vậy:

- Không gọi `db.setProfilingLevel(2)` trên mongos như cách bật profiling cho tất cả shards.
- Tập trung diagnostic logs của mongos nếu cần router view.
- Tập trung profiler/logs của từng shard member theo topology.
- Phân biệt operation thực thi trên shard với router-level latency.

### 19.3. Replica set có nhiều members

Ví dụ:

```text
rs0
├── mongo-a PRIMARY
├── mongo-b SECONDARY
└── mongo-c SECONDARY
```

Nếu application có read preference `secondaryPreferred`, một số queries chạy trên secondary, không phải primary.

Bật profiler chỉ trên database của primary rồi kết luận “không có query chậm” có thể bỏ sót workload ở các secondary.

### 19.4. Profiling config được quản lý theo process/database

Các thay đổi runtime trên một mongod không tự đồng bộ toàn cluster theo mọi tình huống. Cần biết:

- Cấu hình profiler theo database trên từng node.
- Slowms/sampleRate có những tác động process-wide.
- Replica set elections có thể đổi target.
- Managed providers có thể điều phối khác.

Không bật tự động tất cả members khi chưa tính tổng overhead.

### 19.5. Sharded cluster và overhead nhân lên

Nếu một query fan-out tới 10 shards và mỗi shard profile operation tương ứng, một user request có thể tạo nhiều records.

Không cộng duration của 10 shards thành một latency end-to-end nếu chúng chạy song song và mongos merge results.

---

## 20. Tính chi phí lưu trữ profiler: mô hình đơn giản

Để đưa ra quyết định có cơ sở, có thể ước lượng:

\[
\text{records/s} \approx \text{ops/s}\times \text{selected fraction}
\]

\[
\text{bytes/s} \approx \text{records/s}\times\text{avg record bytes}
\]

\[
\text{retention seconds} \approx \frac{\text{capped capacity bytes}}{\text{bytes/s}}
\]

**Chỉ là ước lượng.** Selected fraction có thể phụ thuộc threshold, sampleRate, filter, operation types và sự phân bố latency.

### 20.1. Ví dụ một cluster bận rộn

Giả sử một mongod có:

```text
50.000 operations/s
10% vượt threshold
sampleRate = 0.1
Average profile record = 1.5 KiB
```

Ước lượng:

```text
Đủ điều kiện slow:    50.000 × 10% = 5.000 ops/s
Được lấy mẫu:        5.000 × 0.1 = 500 records/s
Khối lượng dữ liệu:   500 × 1.5 KiB = 750 KiB/s
Mỗi giờ:             khoảng 2.6 GiB/giờ
```

Đây là lưu lượng data logic xấp xỉ, không tính toàn bộ storage engine/write amplification.

### 20.2. Nếu bật level 2?

Giả sử record rate gần số operations/s:

```text
50.000 records/s × 1.5 KiB
  = 75.000 KiB/s
  ≈ 73.2 MiB/s
  ≈ 257 GiB/giờ (trước storage overhead)
```

Ngay cả khi capped collection không tiếp tục tăng sau khi đạt giới hạn, server vẫn phải xử lý **rất nhiều writes** và liên tục overwrite records.

### 20.3. Chỉ lưu được bao lâu?

Giả sử capped profile capacity là 256 MiB:

- 750 KiB/s → khoảng 350 giây, chưa tới 6 phút.
- 75.000 KiB/s → chỉ khoảng 3–4 giây về mặt mô hình đơn giản.

Một câu hỏi như “Tại sao không thấy profile lúc 20 phút trước?” có thể được giải thích bởi vòng đời capped collection ngắn.

### 20.4. Không chỉ có disk storage

Chi phí thực tế còn gồm:

- CPU kiểm tra điều kiện profile.
- CPU xây dựng/serialize document.
- WiredTiger cache occupancy.
- Journal/write path.
- Disk I/O.
- Lock/concurrency overhead.
- Cạnh tranh với application writes.
- Query load nếu dashboard đọc `system.profile` thường xuyên.
- Data export nếu ship records sang hệ thống tập trung.
- Encryption/retention/backup compliance của dữ liệu nhạy cảm.

Cần đo **overhead thực**, không chỉ kích thước `system.profile`.

---

## 21. Ảnh hưởng profiler lên CPU, cache, locks và latency

### 21.1. CPU

Để ghi một profile record, server phải thu thập metadata về operation và xây dựng BSON document. Volume lớn có thể tăng CPU.

### 21.2. Storage I/O

Profiler ghi vào MongoDB storage. Một workload đọc rất nhiều có thể trở thành workload vừa đọc vừa ghi thêm khi bật profiler.

### 21.3. WiredTiger cache

Profile records là data/metadata trong storage engine và có thể tác động tới cache theo cấu hình storage. Cạnh tranh cache có thể làm tăng reads/disk activity.

### 21.4. Contention

Nhiều profile writes và queries đọc profile collection có thể tạo pressure. Không nhất thiết mỗi query sẽ chậm do một lock cụ thể, nhưng tổng overhead có thể làm tail latency tăng.

### 21.5. Ảnh hưởng benchmark

Nếu so:

```text
Benchmark A: profiler off
Benchmark B: profiler level 2
```

và thấy B chậm hơn, không thể kết luận “MongoDB query optimizer thay đổi”. Một phần khác biệt là do chi phí instrumentation.

Nếu benchmark nhằm đánh giá production latency, phải ghi rõ profiling configuration và đảm bảo hai lần so sánh tương đương.

### 21.6. Đừng bỏ qua chi phí phân tích profile records

Một dashboard liên tục chạy:

```javascript
db.system.profile.aggregate([
  { $group: { _id: "$ns", count: { $sum: 1 } } }
]);
```

với tần suất cao cũng tiêu tốn resource. Tăng profiling và đồng thời chạy nhiều phân tích trên chính database có thể khuếch đại overhead.

---

## 22. Cân nhắc tính đúng của thống kê khi sampling

### 22.1. Selection bias

Nếu chỉ profile những thao tác vượt 100 ms, tập record đã **có chủ đích thiên về thao tác chậm**.

Tính:

```javascript
db.system.profile.aggregate([
  {
    $group: {
      _id: null,
      avgMillis: { $avg: "$millis" }
    }
  }
]);
```

sẽ cho **average duration của các records được profile**, không phải average latency của toàn bộ application workload.

### 22.2. Percentile bị méo

Nếu chỉ có thao tác chậm:

- p50 của profiler có thể gần threshold hoặc lớn hơn.
- Nó không phải p50 của mọi queries.
- Tính p95 từ một sample nhỏ có thể rất bất ổn.
- Không nên dùng đó làm KPI production chính thức.

### 22.3. Rare slow queries

Một shape chỉ xảy ra một lần và sampleRate 0.1 có thể không xuất hiện. Không tìm thấy profile record không chứng minh operation không xảy ra.

### 22.4. Khi cần histogram đầy đủ

Sử dụng metrics/histograms từ hệ thống application/driver/monitoring được thiết kế để đo thời gian theo toàn bộ traffic, kết hợp profiler cho những mẫu có thông tin plan.

### 22.5. So sánh giữa các giai đoạn

Ghi rõ tại mỗi mốc:

- Profiler level.
- Slow threshold.
- SampleRate.
- Filter.
- Server version.
- Workload mix.
- Query shape distribution.
- Cluster nodes đang đo.

Nếu các điều kiện khác nhau, chỉ so raw number of profile records rất dễ dẫn tới sai kết luận.

---

## 23. Bảo mật: profiler có thể lưu gì?

Một profile record có thể chứa thông tin của `command`, ví dụ:

```javascript
db.customers.find({
  email: "customer@example.com",
  phone: "0900000000"
});
```

Nếu profiler ghi đủ command payload, có thể lưu:

- Email.
- Số điện thoại.
- Identifiers của tenant/user.
- Giá trị filter/query.
- Một phần update data.
- Tên collections.
- Những thuộc tính nghiệp vụ nhạy cảm.

**Không coi `system.profile` là dữ liệu vô hại chỉ vì nằm trong MongoDB.**

### 23.1. Rủi ro khi bật level 2

Level 2 có thể thu nhiều hơn những thao tác bình thường không chậm, tức là lượng dữ liệu nhạy cảm được lưu/ghi tăng mạnh.

### 23.2. Sanitize trước khi chia sẻ

Thay vì gửi profile document nguyên vẹn vào ticket:

```javascript
{
  ns: "shop.customers",
  command: {
    find: "customers",
    filter: { email: "customer@example.com" }
  },
  docsExamined: 200000,
  nreturned: 1,
  millis: 180
}
```

nên dùng bản đã xử lý:

```json
{
  "ns": "shop.customers",
  "queryShape": {
    "filterFields": ["email"]
  },
  "planSummary": "COLLSCAN",
  "docsExamined": 200000,
  "nReturned": 1,
  "durationMillis": 180
}
```

Vẫn có thể xem query shape và performance counters mà không lộ email.

### 23.3. RBAC

- Chỉ account điều tra được phép đọc `system.profile`.
- Account vận hành bật profiler có privilege tối thiểu.
- Không gán root cho Java API chỉ để truy vấn profiler.
- Audit quyền truy cập dữ liệu nhạy cảm.
- Không export profile documents sang public dashboards.

### 23.4. Encryption và retention

Nếu export profile records:

- Mã hóa trong vận chuyển và khi lưu.
- Quản lý retention.
- Phân quyền, audit.
- Không giữ raw query parameters lâu hơn cần.
- Có quy trình xóa theo yêu cầu privacy/compliance.

### 23.5. Redaction

Một số MongoDB editions/deployments hỗ trợ các tùy chọn redaction client log data. **Không tự suy ra log redaction bảo đảm mọi field trong system.profile sẽ được ẩn theo cùng cách**; cần xác minh quy tắc riêng của profiler và hệ thống export.

---

## 24. MongoDB profiler không phải security audit

Profiler được thiết kế cho **hiệu năng**, không phải log bảo mật toàn vẹn.

Vì sao?

- Level 1 chỉ ghi operations được chọn.
- Sampling có thể bỏ sót.
- Collection capped overwrite records cũ.
- Một số operation types/internal events không được profile theo cách cần cho audit.
- Users được cấp quyền có thể thay đổi configuration.
- Content nhạy cảm có thể được truncate/redacted.

Nếu tổ chức cần truy vết:

- Ai đọc dữ liệu nào?
- Ai thay đổi roles?
- Ai thực hiện thao tác quản trị?
- Thời điểm nào user đăng nhập thất bại?

thì cần database auditing được hỗ trợ và một policy audit/retention cụ thể, **không dùng profiler như nguồn duy nhất**.

---

## 25. Query profiling trong Java Sync Driver

Java application thường không nên tự động bật profiler trên database production. Thay vào đó, ứng dụng nên:

- Đo command latency bằng driver command monitoring.
- Ghi query shape/operation name đã sanitized.
- Dùng distributed tracing và metrics.
- Để DBA/platform team quản lý profiler với change control.

### 25.1. CommandListener minh họa

Ví dụ Java Sync Driver với SLF4J:

```java
import com.mongodb.event.CommandFailedEvent;
import com.mongodb.event.CommandListener;
import com.mongodb.event.CommandStartedEvent;
import com.mongodb.event.CommandSucceededEvent;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.concurrent.TimeUnit;

public final class MongoTimingListener implements CommandListener {
    private static final Logger LOG =
            LoggerFactory.getLogger(MongoTimingListener.class);

    @Override
    public void commandStarted(CommandStartedEvent event) {
        LOG.debug(
            "mongo.start command={} db={} requestId={}",
            event.getCommandName(),
            event.getDatabaseName(),
            event.getRequestId()
        );
    }

    @Override
    public void commandSucceeded(CommandSucceededEvent event) {
        LOG.debug(
            "mongo.success command={} requestId={} elapsedMs={}",
            event.getCommandName(),
            event.getRequestId(),
            event.getElapsedTime(TimeUnit.MILLISECONDS)
        );
    }

    @Override
    public void commandFailed(CommandFailedEvent event) {
        LOG.warn(
            "mongo.failed command={} requestId={} elapsedMs={} type={}",
            event.getCommandName(),
            event.getRequestId(),
            event.getElapsedTime(TimeUnit.MILLISECONDS),
            event.getThrowable().getClass().getSimpleName()
        );
    }
}
```

Lưu ý:

- Không log `event.getCommand()` mặc định trên production.
- `requestId` ở đây là driver command request ID, không phải trace ID end-to-end.
- `elapsedMs` do client/driver quan sát, không giống hoàn toàn `system.profile.millis`.
- Cần dùng metrics/sampling để tránh log một dòng mỗi command ở tần suất cao.
- Exception text/full stack cũng cần được sanitize theo policy.

### 25.2. Đăng ký listener

```java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;

public final class MongoClientFactory {
    public static MongoClient create() {
        String uri = System.getenv("MONGODB_URI");

        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException(
                    "MONGODB_URI must be provided");
        }

        MongoClientSettings settings =
                MongoClientSettings.builder()
                        .applyConnectionString(
                                new ConnectionString(uri))
                        .addCommandListener(new MongoTimingListener())
                        .build();

        return MongoClients.create(settings);
    }
}
```

Không hardcode username/password trong source. URI chứa secret cũng phải được bảo vệ khỏi log, crash dump và truy cập trái phép.

### 25.3. Gắn comment có kiểm soát

Để liên hệ operation ở ứng dụng với server-side observability, MongoDB hỗ trợ `comment` cho nhiều commands.

Ví dụ:

```java
import static com.mongodb.client.model.Filters.eq;

orders.find(eq("status", "PENDING"))
      .comment("service=checkout;operation=listPending")
      .limit(20)
      .into(new java.util.ArrayList<>());
```

Các comment phải:

- Ngắn.
- Không chứa PII/tokens/password.
- Có convention thống nhất.
- Không lạm dụng per-request unique strings nếu có rủi ro cardinality.
- Chỉ dùng khi command/driver/server version hỗ trợ.
- Không coi nó là trace ID được bảo đảm xuất hiện trong mọi profiler record.

### 25.4. Client duration khác profiler millis

Ví dụ:

```text
Java CommandSucceeded.elapsedMs = 400
MongoDB system.profile.millis    = 250
HTTP endpoint latency            = 650
```

Điều đó không đủ để kết luận chính xác 150 ms là network latency. Cần xem connection pools, retries, cursor batches, serialization và tracing spans.

### 25.5. Không cho web request trực tiếp gọi setProfilingLevel()

Nếu ứng dụng nhận API:

```text
POST /admin/enable-profiler?level=2
```

cần nhiều lớp bảo vệ:

- Authentication/authorization admin.
- Change approval.
- Fixed allowed environments.
- Time-limited lease.
- Audit.
- Bounded levels/thresholds.
- Automatic rollback.
- Quota/rate limiting.
- Monitoring overhead.

Tốt hơn là vận hành qua privileged runbook/tool thay vì mở endpoint công khai.

---

## 26. Xử lý trường hợp getMore và cursor

MongoDB có thể tách một truy vấn thành các commands:

```text
find → firstBatch
getMore → secondBatch
getMore → thirdBatch
...
```

Một profiler record cho `find` không nhất thiết phản ánh toàn bộ thời gian đọc qua cursor.

### 26.1. Ví dụ batchSize

```javascript
const lab = db.getSiblingDB("profile_lab");

const allOrders = lab.orders.find({
  tenantId: "t1"
}).batchSize(2).toArray();

print(allOrders.length);
```

Trong những trường hợp có nhiều batches, driver có thể gửi `getMore` để lấy tiếp.

### 26.2. Vì sao cần xem getMore records?

Nếu API đang đọc hàng triệu documents:

- First batch có thể nhanh.
- Những getMore sau có thể chậm vì scan/network/payload.
- Việc chỉ tìm profiler record `op:"query"` sẽ bỏ sót phần đáng kể.

### 26.3. Cursor identifiers

Một số records có `cursorid` hoặc thông tin cursor. Có thể dùng chúng để đối chiếu nhưng:

- Không bảo đảm mọi record có cùng field.
- Connection/cursor lifecycle phức tạp.
- Sharded/mongos paths có nhiều commands.
- Không tự coi cursorid là HTTP request ID.

### 26.4. Quy trình kiểm tra

1. Xem profiler records của `find` và `getmore` liên quan.
2. So duration và batch sizes.
3. So driver spans/end-to-end request.
4. Xem query pagination/projection.
5. Đánh giá batchSize phù hợp với UX/network.
6. Xem liệu service cần lấy toàn bộ documents không.

---

## 27. Khi nào profiler vẫn chưa đủ?

### 27.1. High CPU nhưng không có slow records

Có thể do:

- Mỗi query chạy 30 ms nhưng có hàng trăm nghìn queries/s.
- Ngưỡng slowms 100 ms.
- Sampling thấp.
- Tải từ background tasks/index builds.
- CPU dành cho compression/replication.
- Driver requests dồn quá nhiều.

Cần thêm throughput, serverStatus, resource metrics.

### 27.2. Disk I/O tăng

Profiler có thể cho thấy scans lớn nhưng không cho biết đầy đủ filesystem latency và các storage-level constraints. Cần OS/storage metrics, WiredTiger cache stats và disk throughput.

### 27.3. Lỗi kết nối/TLS

Nếu client không kết nối được, operation có thể chưa đến MongoDB để profiler ghi. Xem diagnostic network/access logs, driver exceptions và infrastructure metrics.

### 27.4. Lock/replication lag

Một số profiler records chứa lock info, nhưng full diagnosis cần thêm:

- currentOp.
- Replication status/lag.
- Write concern.
- Flow control metrics.
- Storage latency.
- Cluster topology.

### 27.5. Sharded cluster

Một query chậm do scatter-gather có thể sinh records trên nhiều shards. Cần router logs, shard targeting và query routing context.

### 27.6. Query chạy quá lâu, chưa hoàn tất

Profiler thường ghi record sau khi operation có thể được ghi nhận. Để xem thao tác **đang chạy**, dùng `currentOp`/monitoring phù hợp với quyền.

Ví dụ mongosh với quyền:

```javascript
db.getSiblingDB("admin").aggregate([
  { $currentOp: { allUsers: false } },
  {
    $match: {
      active: true
    }
  },
  {
    $project: {
      opid: 1,
      ns: 1,
      secs_running: 1,
      op: 1
    }
  },
  { $limit: 20 }
]);
```

Behavior/permissions khác theo topology/version. Không dùng một currentOp output như lịch sử đầy đủ của operations.

---

## 28. Profiler trên Atlas và managed MongoDB

Managed MongoDB có thể cung cấp:

- Query Profiler UI.
- Performance Advisor.
- Slow Query Logs.
- Real-Time Performance Panel.
- Metrics/alerting.
- Backup/monitoring data.

Tính năng/permissions phụ thuộc tier, deployment và product version.

### 28.1. Đừng giả định có thể chỉnh mọi mongod parameter

Trên Atlas, MongoDB Operator hoặc cloud-managed services, trực tiếp chỉnh `mongod.conf` có thể không khả thi hoặc không được hỗ trợ.

Theo hướng dẫn chính thức của dịch vụ, tránh thay đổi cấu hình ngoài control plane.

### 28.2. UI profiler không nhất thiết là system.profile trực tiếp

Một dashboard Query Profiler có thể dùng các nguồn logs/metrics riêng và có thời gian lưu/sampling khác với `system.profile` đọc qua `mongosh`.

Không suy ra mọi event hiển thị trong UI sẽ có document giống hệt trong database.

### 28.3. Managed tier có thể giới hạn

- Khả năng bật profiling level.
- Loại log được tải.
- Khoảng thời gian lưu dữ liệu.
- Quyền quản trị.
- Data redaction/retention.
- Những counters hiển thị.

Đừng dùng kết quả của một shared tier làm bảo đảm cho production dedicated tier hoặc ngược lại.

---

## 29. Dữ liệu trước/sau khi bật profiler: cách đo overhead

Muốn biết profiler ảnh hưởng bao nhiêu, phải đo có kiểm soát.

### 29.1. Chỉ số theo dõi

Trước khi bật:

- Application p50/p95/p99 latency.
- MongoDB operations/s.
- CPU usage.
- Storage IOPS/latency.
- WiredTiger cache.
- Replication lag.
- Disk free.
- System profile write rate.
- Diagnostic log bytes/s.
- Errors/timeouts.

Sau khi bật, đo cùng các chỉ số và ghi thời gian thay đổi.

### 29.2. So sánh công bằng

Nếu traffic tăng gấp đôi cùng lúc bạn bật profiling, không thể quy toàn bộ sự gia tăng CPU cho profiler.

Cần so ở:

- Traffic tương đương.
- Cùng query mix.
- Cùng index/schema.
- Cache/host/topology tương tự.
- Cùng MongoDB version.
- Thời gian đo đủ để giảm nhiễu.

### 29.3. Mô hình thử nghiệm khuyến nghị

```text
Baseline: profiler off
  │
  ├─ metrics/latency baseline
  │
Targeted profiler level 1
  │
  ├─ thu thập 2–5 phút lab hoặc cửa sổ được phê duyệt
  ├─ theo dõi overhead
  │
Restore configuration
  │
  ├─ xác nhận metrics hồi phục
  │
Analyze sanitized records
```

Thời lượng 2–5 phút ở đây là **ví dụ mô hình lab**, không phải khuyến nghị cố định cho production; thực tế phụ thuộc traffic/risk và approval.

### 29.4. Thiết lập tiêu chí dừng

Ví dụ:

- CPU tăng vượt budget được phê duyệt.
- MongoDB p99 tăng đáng kể.
- Disk free xuống ngưỡng nguy hiểm.
- Replication lag tăng quá mức.
- Profile record writes vượt giới hạn.
- Collector/log pipeline bị backpressure.

Cần dừng và khôi phục trước khi profiler làm sự cố nặng hơn.

---

## 30. Runbook: điều tra query latency tăng bằng profiler

### Bước 1 — Xác định triệu chứng

Ghi:

- API/query shape nào?
- Thời gian sự cố?
- Host/cluster/shard?
- SLO bị vi phạm?
- Có deploy/schema/index migration gần đó không?

### Bước 2 — Dùng tín hiệu chi phí thấp trước

- Application metrics/traces.
- MongoDB diagnostic slow logs.
- CPU/cache/disk.
- Query explain ở môi trường an toàn.
- currentOp nếu đang có long-running operation.

Nếu đủ dữ liệu, **không cần bật profiler**.

### Bước 3 — Đánh giá rủi ro bật profiler

- Workload operations/s?
- Bao nhiêu databases dùng chung mongod?
- Có user data trong query payload?
- Quyền quản trị có phù hợp?
- Tốc độ writes/storage cho system.profile?
- Có replication/HA impact không?
- Incident có cần data từ secondary/shards không?

### Bước 4 — Snapshot configuration

```javascript
const target = db.getSiblingDB("commerce");
printjson(target.getProfilingStatus());
```

Lưu level, slowms, sampleRate, filter, thời điểm và process.

### Bước 5 — Bật level 1 có kiểm soát

Trên môi trường được phê duyệt:

```javascript
target.setProfilingLevel(1, {
  slowms: 100,
  sampleRate: 0.1
});
```

Đây chỉ là tham số minh họa. Chọn threshold/sample phù hợp workload; nếu đã có filter, xem interaction.

### Bước 6 — Theo dõi overhead

Theo dõi trong quá trình lấy mẫu:

- p95/p99.
- CPU.
- Disk I/O.
- Profile records/s.
- Free disk/capped wrap rate.
- Replication lag.
- Thời gian log pipeline ingest.

Nếu vượt giới hạn, rollback ngay.

### Bước 7 — Đọc records an toàn

```javascript
target.system.profile.find(
  { ns: "commerce.orders" },
  {
    ts: 1,
    op: 1,
    ns: 1,
    millis: 1,
    keysExamined: 1,
    docsExamined: 1,
    nreturned: 1,
    planSummary: 1
  }
).sort({ ts: -1 }).limit(30);
```

Chỉ đọc field cần thiết, tránh in `command` có dữ liệu nhạy cảm ra terminal/ticket công khai.

### Bước 8 — Phân tích và kiểm chứng

- Group theo namespace/query shape nếu identifier hợp lệ.
- Tìm records có scan ratio cao hoặc duration bất thường.
- Dùng explain tương ứng.
- Đánh giá index/queries/traffic skew.
- Kiểm tra lock/IO/replication yếu tố liên quan.
- So với application traces và timeout metrics.

### Bước 9 — Khắc phục có kiểm soát

Có thể:

- Thêm index phù hợp query shape.
- Sửa điều kiện filter.
- Bổ sung tenant/shard key predicate.
- Giảm returned documents bằng pagination/projection.
- Sửa sort/aggregation pipeline.
- Điều chỉnh batch sizes.
- Tách workload analytics.
- Thay đổi API behavior khi đúng nghiệp vụ.

Đừng chỉ tăng phần cứng khi chưa hiểu nguyên nhân.

### Bước 10 — Khôi phục profiler

- Restore chính xác level.
- Restore slowms/sampleRate/filter.
- Xác minh các databases/processes bị ảnh hưởng.
- Kiểm tra CPU/disk/log volume trở về baseline.
- Lưu evidence đã sanitize.
- Ghi incident report và cập nhật cảnh báo.

---

## 31. Mẫu change record cho profiler

Trước khi thay đổi, điền:

| Trường | Nội dung |
|---|---|
| Incident/Change ID | Mã thay đổi |
| Owner | Người chịu trách nhiệm |
| Environment | Production/Staging/Lab |
| MongoDB Server version | Phiên bản thực tế |
| Cluster/Replica set | Tên topology |
| Target process | Host/pod/instance |
| Database | Database sẽ bật profiler |
| Current level | 0/1/2 |
| Current slowms | Giá trị hiện tại |
| Current sampleRate | Giá trị hiện tại |
| Current filter | Điều kiện hiện tại hoặc none |
| Proposed level | 1 hoặc 2 có lý do |
| Proposed slowms/sampleRate/filter | Chỉ định rõ |
| Expected records/s | Ước lượng |
| Capped capacity | Dung lượng thực |
| Sensitive data controls | RBAC/redaction |
| Stop condition | CPU, p99, storage, lag |
| Rollback owner | Người thực hiện |
| Rollback commands | Lệnh khôi phục đã được review |
| Validation | Metrics và trạng thái sau rollback |

Không dùng một ticket không có owner/cửa sổ rollback cho việc bật level 2 trên production.

---

## 32. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `system.profile` rỗng | Level 0 | Kiểm tra getProfilingStatus |
| `system.profile` rỗng khi level 1 | Không query nào vượt slowms | So threshold/workload |
| Một số query không xuất hiện | Sampling loại bỏ | Không coi là missing operation chắc chắn |
| Filter theo namespace không có record | Filter sai/namespace khác | Đối chiếu ns/schema/version |
| Server log có slow query nhưng profile rỗng | Profiler và diagnostic logs khác nhau | Đọc level/slow settings |
| Profile data cũ biến mất | Capped collection overwrite | Ước lượng retention, export có kiểm soát |
| CPU tăng sau level 2 | Instrumentation overhead | Tắt/giảm profiling |
| Disk I/O tăng mạnh | Profile writes và các writes khác | Tính records/s/storage pressure |
| Log storm ở database khác | slowms/sampleRate có tác động process-wide | Khôi phục global settings |
| Tắt level 2 nhưng còn nhiều slow logs | slow logging độc lập profiler | Xem threshold/filter/diagnostic log |
| Avg millis tăng khi giảm slowms? | Selection bias thay đổi | So histogram metrics đầy đủ |
| Không có query values trong record | Truncation/redaction/field optional | Không mặc định profiler chứa full command |
| Thấy `COLLSCAN` và lập tức tạo index | Có thể query scan nhỏ/hợp lý | Explain + workload |
| Thấy `IXSCAN` và kết luận đã tối ưu | Index range có thể rộng | KeysExamined/nReturned |
| Profiler record millis khác HTTP latency | Timing layers khác nhau | Driver/APM traces |
| App dùng secondary nhưng xem primary | Sai process | Theo read preference/topology |
| Mongos không có system.profile | Profiler nằm trên mongod | Dùng router/shard observability |
| Bật debug trên Atlas bị từ chối | Managed tier/role restrictions | Dùng UI/API được hỗ trợ |
| Failed unauthorized khi đọc profile | Thiếu privilege | Dùng RBAC đúng, không gán root bừa |
| Đã bật level 1 nhưng không thấy getMore | Query đủ nhỏ hoặc filter loại | Xem batching và event types |
| Quên rollback filter | Sampling/threshold hành vi khác | Khôi phục full profiling config |
| Lộ thông tin khách hàng qua export | Command payload chứa PII | Sanitize, RBAC, retention |
| Profiling level 2 làm benchmark chậm | Instrumentation thay đổi workload | Đo baseline và so công bằng |

---

## 33. Bài tập A — Phân biệt profiler và slow log

Cho trạng thái:

```text
Profiler level: 0
slowms: 100
sampleRate: 1.0
```

Trả lời:

1. MongoDB có ghi records mới vào `system.profile` không?
2. Server diagnostic log có thể ghi slow operations không?
3. Một query 200 ms luôn có profile record không?
4. Lệnh nào kiểm tra profile level?
5. Vì sao người vận hành có thể thấy `Slow query` trong mongod.log nhưng không có `system.profile` record?

## 34. Bài tập B — Level 1 và Level 2

Một node thực thi 20.000 queries/s. Trong đó 2% vượt 100 ms.

1. Ước lượng số operations đủ điều kiện ở level 1 với slowms 100.
2. Nếu sampleRate là 0.1, ước lượng records/s theo mô hình đơn giản.
3. Với level 2, rủi ro là gì?
4. Cần theo dõi CPU, disk và p99 như thế nào?
5. Vì sao không thể lấy số profile records để suy ra số HTTP requests chính xác?

## 35. Bài tập C — Đọc system.profile

Dùng `profile_lab.orders`:

1. Đọc `getProfilingStatus()`.
2. Bật level 1 trên isolated lab.
3. Chạy vài `find` và `aggregate`.
4. Truy vấn `system.profile` với projection chỉ lấy metadata.
5. Giải thích vì sao records có thể rỗng nếu dataset quá nhỏ.
6. Nếu được phép, tạm bật level 2 trên lab và đọc vài records.
7. Khôi phục trạng thái.

## 36. Bài tập D — Phân tích record

Cho record minh họa:

```javascript
{
  op: "query",
  ns: "shop.orders",
  planSummary: "COLLSCAN",
  keysExamined: 0,
  docsExamined: 300000,
  nreturned: 8,
  millis: 930
}
```

Hãy:

1. Tính scan ratio.
2. Nêu hai giả thuyết nguyên nhân.
3. Đề xuất query/explain cần kiểm tra.
4. Vì sao chưa thể chắc chắn index thiếu?
5. Những metrics nào cần đối chiếu?

## 37. Bài tập E — Sampling và thống kê

Một dashboard cho thấy:

```text
Ngày 1:
  sampleRate: 1.0
  Profile records: 10.000

Ngày 2:
  sampleRate: 0.1
  Profile records: 1.100
```

Có thể nói query workload giảm 89% không? Giải thích sampling bias, threshold, query mix và metrics độc lập cần dùng.

## 38. Bài tập F — Filter

Trong một phiên bản hỗ trợ profile filter:

1. Thiết kế filter chỉ chọn collection `orders`.
2. Ước lượng operations/s của collection.
3. Giải thích interaction giữa filter, slowms và sampleRate.
4. Trình bày cách đọc trạng thái effective.
5. Thiết kế rollback cho filter.

## 39. Bài tập G — Storage budget

Một mongod có:

```text
Profiler capped capacity: 128 MiB
Average record size:      2 KiB
Profile records rate:     250/s
```

Tính thời gian lưu lý thuyết trước khi overwrite. Đưa ra ít nhất ba biện pháp giảm overhead mà không cần tăng dung lượng vô hạn.

## 40. Bài tập H — Java Driver correlation

Một Java API có:

```text
HTTP duration:         1200 ms
Driver command:         850 ms
Profiler millis:        600 ms
```

Giải thích:

1. Ba phép đo khác nhau ở đâu?
2. Có thể kết luận 250 ms là network hoàn toàn không?
3. getMore/retries ảnh hưởng thế nào?
4. Tại sao không nên log `event.getCommand()`?
5. Làm sao sử dụng trace/comment một cách an toàn?

## 41. Bài tập I — Replica set và sharding

Một cluster có:

```text
mongos-1
  ├── shardA: rsA
  ├── shardB: rsB
  └── shardC: rsC
```

Trả lời:

1. Có thể bật profiler trên mongos như trên mongod không?
2. Nếu chỉ xem primary shardA, bỏ sót query nào?
3. Một query scatter-gather có thể tạo bao nhiêu records?
4. Vì sao không cộng duration của các shards thành request duration?
5. Những labels nào cần dùng khi tổng hợp logs/profile?

## 42. Bài tập J — Incident runbook

API p99 tăng sau deploy. Nhóm định bật profiler level 2 trên toàn cluster trong 24 giờ.

Hãy viết phương án thay thế an toàn:

1. Sử dụng metrics/slow logs ban đầu.
2. Tính query traffic và storage budget.
3. Xem profiler status của đúng mongod/database.
4. Chọn level/filter/sample nhỏ hơn nếu được.
5. Đặt thời gian và stop conditions.
6. Bảo vệ PII.
7. Lấy records/explain.
8. Rollback và xác minh.
9. Ghi incident report đã sanitize.

## 43. Bài tập K — Observability cost vs value

Đề xuất chính sách cho ba loại môi trường:

- **Dev laptop:** Có thể bật level 2 ngắn khi cần, traffic thấp.
- **Staging:** Level 1 có mục tiêu rõ, kiểm soát retention.
- **Production:** Mặc định ưu tiên low-overhead monitoring và chỉ bật targeted profiling theo runbook.

So sánh mức độ chi tiết, volume, privacy và khả năng phản ứng sự cố.

---

## 44. Checklist trước khi bật profiler

### 44.1. Mục tiêu điều tra

- [ ] Biết câu hỏi cần trả lời.
- [ ] Đã xem slow diagnostic logs và metrics có sẵn.
- [ ] Đã kiểm tra query shape/explain an toàn.
- [ ] Có lý do cụ thể phải dùng profiler.
- [ ] Xác định đúng database và process.

### 44.2. Cấu hình

- [ ] Ghi lại current profile level.
- [ ] Ghi lại current slowms.
- [ ] Ghi lại current sampleRate.
- [ ] Ghi lại current filter và semantics.
- [ ] Hiểu slowms/sampleRate có thể ảnh hưởng rộng hơn database.
- [ ] Có phiên bản MongoDB Server cụ thể.
- [ ] Xác nhận managed deployment có hỗ trợ.

### 44.3. Chi phí

- [ ] Ước lượng operations/s.
- [ ] Ước lượng fraction đủ điều kiện.
- [ ] Ước lượng profile record size.
- [ ] Xem capped collection capacity và retention.
- [ ] Có headroom CPU/disk/cache.
- [ ] Có monitoring p95/p99/replication lag.
- [ ] Có stop conditions.
- [ ] Không bật level 2 kéo dài trên production.

### 44.4. Bảo mật

- [ ] Có RBAC đọc/chỉnh profiler.
- [ ] Không in raw customer PII vào ticket.
- [ ] Không log secrets.
- [ ] Tránh export query payload không kiểm soát.
- [ ] Có encryption/retention policy.
- [ ] Không coi profiler là audit trail.

### 44.5. Khi tắt

- [ ] Trả profile level về giá trị cũ.
- [ ] Khôi phục slowms/sampleRate.
- [ ] Khôi phục filter nếu có.
- [ ] Xác minh trên các processes/databases liên quan.
- [ ] Theo dõi log/profile write rate giảm.
- [ ] Giữ evidence đã sanitize.
- [ ] Cập nhật runbook.

---

## 45. Những nhầm lẫn phổ biến cần ghi nhớ

| Nhầm lẫn | Thực tế |
|---|---|
| Profiler là mongod.log | Profiler ghi `system.profile` |
| Level 0 tắt mọi slow query logging | Diagnostic log có thể vẫn ghi |
| Level 1 chỉ ảnh hưởng database đang gọi theo mọi tham số | slowms/sampleRate có tác động process/global |
| Level 2 luôn tốt nhất | Chi phí CPU/write/storage và privacy có thể rất lớn |
| system.profile chứa mọi query vĩnh viễn | Đây là capped collection |
| sampleRate 0.1 cho đúng 10% ở mọi nhóm nhỏ | Sampling có biến động |
| Profile count giảm nghĩa là app nhanh lên | Có thể do sampling/threshold đổi |
| `avg(millis)` từ level 1 là latency trung bình toàn hệ thống | Chỉ là tập chọn lọc |
| Không có record là không có query chậm | Có filter/sample/threshold/target sai |
| Filter + sampleRate luôn cùng giới hạn như khi không filter | Filter có thể làm slowms/sampleRate không áp dụng theo cơ chế thường |
| `IXSCAN` đồng nghĩa tối ưu | Có thể quét rất nhiều keys |
| `COLLSCAN` luôn sai | Với tập nhỏ/analytics, có thể hợp lý |
| `millis` giống HTTP latency | Chỉ server-side operation timing |
| Profiler tự chẩn đoán root cause | Cần explain, metrics và workload context |
| Tăng capped size giải quyết mọi vấn đề | Không xóa CPU/I/O overhead |
| system.profile không nhạy cảm | Có thể chứa query/update values và PII |
| Profiler thay auditing | Không có completeness/durability guarantee cho audit |
| Java command monitoring giống profiler | Client-side vs server-side khác nhau |
| Mongos có system.profile như mongod | Không |
| Bật trên một primary quan sát mọi read | Reads có thể chạy trên secondary |
| Cứ tắt level 2 là khôi phục toàn bộ config | Còn slowms/sampleRate/filter |
| Query record có đủ mọi field | Schema tùy version/operation |
| Dùng profiler để đo benchmark không ảnh hưởng kết quả | Instrumentation có thể làm lệch benchmark |

---

## 46. Tài liệu MongoDB chính thức

- [MongoDB Manual – Database Profiler](https://www.mongodb.com/docs/manual/tutorial/manage-the-database-profiler/)
- [MongoDB Manual – Database Profiler Output](https://www.mongodb.com/docs/manual/reference/database-profiler/)
- [MongoDB Manual – db.setProfilingLevel()](https://www.mongodb.com/docs/manual/reference/method/db.setProfilingLevel/)
- [MongoDB Manual – db.getProfilingStatus()](https://www.mongodb.com/docs/manual/reference/method/db.getProfilingStatus/)
- [MongoDB Manual – db.getProfilingLevel()](https://www.mongodb.com/docs/manual/reference/method/db.getProfilingLevel/)
- [MongoDB Manual – profile Command](https://www.mongodb.com/docs/manual/reference/command/profile/)
- [MongoDB Manual – operationProfiling Configuration](https://www.mongodb.com/docs/manual/reference/configuration-options/#operationprofiling-options)
- [MongoDB Manual – Log Messages](https://www.mongodb.com/docs/manual/reference/log-messages/)
- [MongoDB Manual – Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Manual – currentOp Aggregation](https://www.mongodb.com/docs/manual/reference/operator/aggregation/currentOp/)
- [MongoDB Manual – serverStatus Command](https://www.mongodb.com/docs/manual/reference/command/serverStatus/)
- [MongoDB Java Sync Driver – Monitoring and Logging](https://www.mongodb.com/docs/drivers/java/sync/current/monitoring-and-logging/)
- [MongoDB Atlas – Query Profiler](https://www.mongodb.com/docs/atlas/tutorial/profile-database/)
- [MongoDB Atlas – Monitoring and Alerts](https://www.mongodb.com/docs/atlas/monitoring-alerts/)

> **Lưu ý phiên bản:** Profiler records, các trường query shape/plan identifiers, filters, phạm vi server-wide của parameters và khả năng tùy chỉnh trên managed deployments phụ thuộc MongoDB Server/Atlas tier. Với môi trường thật, hãy đối chiếu tài liệu của phiên bản và hạ tầng đang sử dụng trước khi đổi cấu hình. Ví dụ trong bài là hướng dẫn học tập, không phải script chạy nguyên xi trên production.

---

## 47. Kết luận

1. **Database profiler** giúp quan sát operations ở tầng MongoDB Server bằng những documents trong `<database>.system.profile` trên `mongod`.
2. **Level 0** tắt profile records, **level 1** thu thập theo ngưỡng/filter, **level 2** ghi rộng và có nguy cơ overhead lớn.
3. `slowms` và `sampleRate` không nên được hiểu chỉ ảnh hưởng một database; thay đổi của chúng có thể ảnh hưởng slow logging ở mức process.
4. **Profiling filter** là công cụ chọn lọc mạnh nhưng cần hiểu rõ cách nó tương tác với threshold/sampling.
5. `system.profile` là **capped collection**: khi rate cao, records cũ bị overwrite nhanh, không phù hợp lưu lịch sử/audit vô hạn.
6. Chi phí thu thập gồm **CPU, storage writes, cache, disk I/O, vận hành và bảo mật**, không chỉ dung lượng records.
7. Profiler data là **sample/selection**, nên averages/percentiles tính từ đó không tự đại diện cho toàn bộ workload.
8. Đọc `millis`, `ns`, `planSummary`, `keysExamined`, `docsExamined` và `nreturned` rồi kiểm chứng bằng `explain()` và metrics.
9. **Không coi raw command/profile data là vô hại**: nó có thể chứa PII và business secrets.
10. Luôn thiết kế profiling như một **thay đổi có chủ đích, giới hạn thời gian, có monitoring và rollback**.

**Nguyên tắc vận hành:** Chỉ thu thập **đủ dữ liệu để trả lời câu hỏi điều tra**. Profiler tốt nhất là profiler đem lại bằng chứng hữu ích mà không trở thành một nguồn tải hoặc rủi ro bảo mật mới đối với MongoDB.
