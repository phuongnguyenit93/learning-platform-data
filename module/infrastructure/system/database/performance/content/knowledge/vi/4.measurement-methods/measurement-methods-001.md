# Thiết lập đường cơ sở trước khi thay đổi truy vấn hoặc cấu hình

Trong tối ưu hiệu năng cơ sở dữ liệu, một thay đổi chỉ có ý nghĩa khi ta biết hệ thống hoạt động ra sao trước và sau thay đổi đó. Nếu chỉ nhìn thấy truy vấn chạy nhanh hơn trong một lần thử, ta chưa thể kết luận hiệu năng đã được cải thiện: lần chạy sau có thể được hưởng lợi từ cache, tải nền có thể đã giảm, dữ liệu đầu vào có thể khác, hoặc một workload khác có thể đang chậm đi.

**Đường cơ sở hiệu năng (performance baseline)** là tập hợp số liệu và điều kiện vận hành được ghi nhận trước khi điều chỉnh truy vấn, chỉ mục hoặc cấu hình. Đường cơ sở tạo mốc tham chiếu để xác định vấn đề, đặt mục tiêu, so sánh kết quả và quyết định có giữ thay đổi hay hoàn tác. Với module `DATABASE_PERFORMANCE`, đây là bước nền tảng của phương pháp tối ưu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu.

Một đường cơ sở có giá trị phải mô tả cả **kết quả quan sát được** lẫn **điều kiện tạo ra kết quả đó**. Thời gian truy vấn riêng lẻ không đủ; cần ghi nhận workload, mức đồng thời, dữ liệu, tài nguyên, trạng thái hệ thống và phạm vi đo. Nếu thiếu bối cảnh, số liệu trước và sau có thể không thể so sánh.

## 1. Đường cơ sở trả lời những câu hỏi nào?

Trước khi thay đổi, nhóm phát triển và vận hành cần trả lời được:

- Hành trình nghiệp vụ hoặc nhóm truy vấn nào đang chậm? Chậm với mọi lần gọi hay chỉ với một số tham số, thời điểm hoặc mức tải?
- Độ trễ quan sát ở ứng dụng là bao nhiêu và phần nào nằm trong thời gian xử lý của cơ sở dữ liệu?
- Hệ thống đang phục vụ bao nhiêu yêu cầu hoặc transaction mỗi giây? Tỷ lệ lỗi, timeout và deadlock ra sao?
- CPU, bộ nhớ, I/O, log, kết nối và khóa được sử dụng như thế nào trong cùng khoảng đo?
- Kế hoạch thực thi đang đọc bao nhiêu dòng, truy cập bao nhiêu trang, lặp qua những nút nào và có dùng vùng dữ liệu tạm hay không?
- Mục tiêu sau thay đổi là gì, và điều kiện nào sẽ khiến ta chấp nhận, điều chỉnh tiếp hoặc hoàn tác?

Đường cơ sở thường có bốn lớp số liệu liên kết với nhau:

| Phạm vi | Ví dụ số liệu | Ý nghĩa |
|---|---|---|
| Ứng dụng và nghiệp vụ | Thời gian phản hồi p50/p95/p99, tỷ lệ lỗi, timeout | Phản ánh trải nghiệm người dùng và kết quả nghiệp vụ |
| Truy vấn hoặc transaction | CPU time, elapsed time, số lần gọi, số dòng, logical reads, execution plan | Cho biết chi phí và cách cơ sở dữ liệu thực hiện công việc |
| Workload | Throughput, số kết nối đồng thời, tỷ lệ đọc/ghi, thời lượng transaction | Mô tả tải thực tế mà hệ thống phải phục vụ |
| Máy chủ và tài nguyên | CPU, bộ nhớ, IOPS, độ trễ lưu trữ, dung lượng tạm, wait event | Cho biết giới hạn tài nguyên và tranh chấp ở cấp hệ thống |

Không phải mọi chỉ số đều cần thiết cho mọi bài toán. Hãy chọn số liệu có thể giúp kiểm chứng giả thuyết đang điều tra và vẫn quan sát được các tác động phụ quan trọng.

## 2. Xác định phạm vi và giả thuyết trước khi đo

### Chọn đúng đối tượng cần cải thiện

Không nên bắt đầu bằng một câu lệnh ngẫu nhiên chỉ vì nó có vẻ phức tạp. Hãy dùng log ứng dụng, APM, thống kê câu lệnh và phản ánh từ người dùng để chọn đối tượng có ảnh hưởng đáng kể. Một truy vấn có thời gian trung bình cao chưa chắc là ưu tiên lớn nhất; một truy vấn chỉ mất vài mili giây nhưng được gọi hàng chục nghìn lần có thể tiêu thụ tổng tài nguyên lớn. Ngược lại, một truy vấn hiếm gặp nhưng nằm trên đường đi của thao tác quan trọng có thể quyết định p99 của trải nghiệm.

Có thể phân loại đối tượng theo các tiêu chí:

- **Tác động nghiệp vụ:** chức năng quan trọng, số người dùng bị ảnh hưởng, mức độ nghiêm trọng khi timeout.
- **Độ trễ:** p50, p95, p99, thời gian tối đa và tỷ lệ yêu cầu vượt SLO.
- **Tổng chi phí:** tổng thời gian thực thi, CPU cộng dồn, số lần gọi và lượng I/O.
- **Mức ổn định:** biến động giữa các lần chạy, phụ thuộc tham số, ảnh hưởng của giờ cao điểm.
- **Khả năng kiểm soát:** có thể tạo dữ liệu và tải đại diện, tái hiện câu lệnh và đo các chỉ số liên quan hay không.

### Viết giả thuyết có thể kiểm chứng

Một giả thuyết tốt nêu rõ dấu hiệu hiện tại, nguyên nhân dự kiến và số liệu sẽ thay đổi nếu nguyên nhân đúng. Ví dụ:

> Truy vấn tra cứu đơn hàng có p95 cao khi khách hàng có nhiều đơn. Execution plan đọc nhiều dòng rồi loại phần lớn bằng bộ lọc. Nếu tạo chỉ mục phù hợp với điều kiện lọc và thứ tự truy cập, số trang phải đọc và p95 sẽ giảm mà throughput ghi vẫn nằm trong giới hạn chấp nhận.

Giả thuyết này dẫn tới những phép đo cụ thể: p95 theo nhóm khách hàng, số dòng thực tế, logical reads hoặc buffer reads, thời gian truy vấn, chi phí cập nhật chỉ mục và throughput của thao tác ghi. Nếu chỉ ghi “thêm index để truy vấn nhanh hơn”, ta chưa xác định được kết quả nào chứng minh thay đổi có hiệu quả.

Trước khi bắt đầu, ghi lại:

1. Đối tượng và hành trình nghiệp vụ cần đo.
2. Triệu chứng hiện tại cùng nguồn phát hiện.
3. Giả thuyết nguyên nhân và số liệu dự kiến thay đổi.
4. Mục tiêu hiệu năng và giới hạn không được làm xấu đi.
5. Điều kiện chấp nhận, điều kiện cần thử tiếp và điều kiện hoàn tác.

## 3. Mô tả workload đại diện

Workload là tập hợp công việc thực tế mà cơ sở dữ liệu phải xử lý trong một khoảng thời gian. Một truy vấn chạy riêng lẻ trên máy ít tải không thể đại diện cho hệ thống đang phục vụ hàng trăm phiên đồng thời. Vì vậy, trước khi đo, cần mô tả tải theo các chiều sau:

| Chiều workload | Nội dung cần ghi nhận |
|---|---|
| Loại thao tác | SELECT, INSERT, UPDATE, DELETE, transaction nghiệp vụ, batch hoặc báo cáo |
| Tần suất | Số lần gọi theo giây/phút, phân bố theo giờ và các đợt tăng đột biến |
| Mức đồng thời | Số session, request đồng thời, connection pool và số worker |
| Phân bố tham số | Giá trị phổ biến, giá trị hiếm, tập dữ liệu nhỏ/lớn và độ lệch phân bố |
| Quy mô dữ liệu | Số dòng, kích thước bảng/chỉ mục, độ tăng trưởng và mức phân mảnh nếu hệ quản trị có khái niệm tương ứng |
| Hỗn hợp đọc/ghi | Tỷ lệ đọc, ghi, commit, transaction dài và thao tác khóa nhiều dòng |
| Hành vi ứng dụng | Batch size, số dòng kết quả, cách phân trang, tốc độ tiêu thụ kết quả và thời gian giữ kết nối |
| Thời điểm | Giờ bình thường, giờ cao điểm, tác vụ định kỳ, backup, ETL hoặc batch nền |

Đặc biệt chú ý độ lệch dữ liệu. Một câu lệnh với tham số trả về 5 dòng có thể dùng kế hoạch rất khác khi tham số khác trả về 500.000 dòng. Nếu chỉ đo một giá trị tham số thuận lợi, đường cơ sở sẽ bỏ qua trường hợp gây ra độ trễ cao. Nên chọn các nhóm tham số đại diện: phổ biến, hiếm, tập kết quả nhỏ, tập kết quả lớn và các trường hợp có phân bố lệch.

Khi không thể tái tạo toàn bộ lưu lượng, hãy xác định rõ phần nào được mô phỏng, phần nào được lấy từ production, và giới hạn suy luận từ phép đo. Không được gọi một workload thử nghiệm nhỏ là đại diện cho tải cao nếu chưa chứng minh được tính tương đồng.

## 4. Chọn chỉ số và quy tắc đo

### Độ trễ và thông lượng

Độ trễ cho biết một yêu cầu mất bao lâu; thông lượng cho biết hệ thống hoàn thành được bao nhiêu công việc trong một đơn vị thời gian. Cần theo dõi cả hai vì một hệ thống có thể giảm độ trễ của từng truy vấn bằng cách xử lý ít yêu cầu hơn, khiến tổng năng lực phục vụ giảm.

Với độ trễ, nên ghi các phân vị:

- **p50 (median):** một nửa yêu cầu hoàn thành nhanh hơn hoặc bằng giá trị này.
- **p95:** 95% yêu cầu hoàn thành trong thời gian không vượt quá giá trị này; phần đuôi chậm hơn cần được xem xét.
- **p99:** giúp quan sát các yêu cầu rất chậm nhưng có thể ít xuất hiện.
- **Tỷ lệ vượt ngưỡng:** số yêu cầu vượt SLO chia cho tổng số yêu cầu trong cùng phạm vi.

Giá trị trung bình (mean) hữu ích khi tính tổng chi phí, nhưng có thể che giấu đuôi phân phối. Không nên dùng riêng mean để đánh giá trải nghiệm. Khi số mẫu nhỏ, p99 dễ biến động; hãy ghi số lượng mẫu và kéo dài cửa sổ đo cho tới khi có đủ dữ liệu đại diện.

Thông lượng cần có đơn vị rõ ràng, ví dụ request/giây, transaction/giây hoặc dòng được xử lý/giây. Không so sánh hai lần đo nếu định nghĩa “một transaction” hoặc khối lượng công việc khác nhau.

### CPU, I/O, bộ nhớ và chờ

Ở cấp truy vấn, thu thập các số liệu có thể liên hệ với execution plan: CPU time, elapsed time, số lần gọi, số dòng đọc và trả về, logical reads, physical reads, buffer hit/read, sort/hash, dữ liệu tạm và thời gian chờ theo loại sự kiện.

Ở cấp hệ thống, ghi nhận CPU sử dụng và hàng đợi CPU, bộ nhớ khả dụng, áp lực bộ nhớ, IOPS, throughput lưu trữ, độ trễ đọc/ghi, hoạt động log, số kết nối, lock wait và deadlock. Các chỉ số phải được quan sát trong cùng cửa sổ với độ trễ và throughput để có thể liên hệ nguyên nhân.

Không được coi `CPU time + wait time = elapsed time` là đẳng thức phổ quát. Các hệ quản trị có cách đo khác nhau; thời gian chờ của nhiều worker có thể cộng dồn và chồng lấp. Hãy ghi tên công cụ, đơn vị, phạm vi và định nghĩa của từng chỉ số.

### Tỷ lệ và chi phí trên một đơn vị công việc

Các tổng số tích lũy nên được chuyển thành mức phát sinh trong cửa sổ đo bằng cách lấy hiệu giữa hai snapshot, sau đó chuẩn hóa theo số transaction hoặc số request hoàn thành. Ví dụ:

```text
CPU trên mỗi transaction = CPU time phát sinh trong cửa sổ / số transaction hoàn thành
I/O trên mỗi transaction = số lần đọc phát sinh trong cửa sổ / số transaction hoàn thành
Tỷ lệ lỗi = số request lỗi trong cửa sổ / tổng request trong cửa sổ
Throughput = số transaction hoàn thành / số giây đo
```

Chuẩn hóa giúp so sánh khi hai cửa sổ có tổng lượng công việc khác nhau. Tuy vậy, chỉ số trên mỗi transaction vẫn cần được đọc cùng mức đồng thời và phân bố loại transaction; một transaction báo cáo lớn không tương đương một transaction tra cứu đơn giản.

## 5. Ghi lại điều kiện môi trường

Số liệu hiệu năng chịu ảnh hưởng mạnh bởi môi trường. Trước mỗi lần đo, cần ghi đủ thông tin để người khác có thể hiểu và tái lập điều kiện thử nghiệm.

| Nhóm thông tin | Nội dung cần ghi |
|---|---|
| Hệ quản trị | Sản phẩm, phiên bản, edition, bản vá và extension liên quan |
| Máy chủ | CPU, số lõi, RAM, kiến trúc, giới hạn container/VM và mức sử dụng tài nguyên |
| Lưu trữ | Loại thiết bị, cấu hình volume, IOPS/throughput giới hạn, độ trễ và vị trí data/log/temp |
| Cấu hình DB | Tham số bộ nhớ, parallelism, connection limit, timeout, checkpoint, log và cấu hình optimizer liên quan |
| Schema | DDL, khóa chính/ngoại, chỉ mục, partition, constraint và kích thước bảng/chỉ mục |
| Thống kê optimizer | Thời điểm cập nhật thống kê, số dòng ước lượng, phân bố dữ liệu và histogram nếu có |
| Dữ liệu | Số dòng, kích thước, độ lệch, mức tăng trưởng và dữ liệu đã được ẩn danh hay sinh tổng hợp |
| Ứng dụng | Phiên bản, connection pool, số worker, timeout, cách phân trang và batch size |
| Trạng thái hệ thống | Cache nóng/lạnh, tác vụ nền, backup, replication lag, vacuum/maintenance và tải đồng thời |
| Phạm vi đo | Mốc bắt đầu/kết thúc, múi giờ, công cụ, tần suất lấy mẫu và bộ lọc |

Không phải tất cả hệ quản trị đều có cùng khái niệm thống kê, cache hoặc cấu hình. Hãy lưu đúng giá trị và cách diễn giải của nền tảng đang sử dụng. Nếu môi trường thử nghiệm có CPU, bộ nhớ hoặc lưu trữ khác production, ghi rõ chênh lệch để tránh suy luận quá mức.

### Cache nóng và cache lạnh

Trạng thái cache có thể làm thay đổi đáng kể thời gian đọc dữ liệu. Khi đo trạng thái cache nóng, cần chạy giai đoạn làm nóng (warm-up) với workload đại diện trước khi lấy số liệu. Khi đo trạng thái cache lạnh, cần có quy trình riêng và môi trường phù hợp.

Không nên xóa cache hoặc khởi động lại máy chủ production chỉ để tạo phép đo cache lạnh. Việc này có thể gây gián đoạn và tạo tải I/O đột biến. Nếu không thể kiểm soát trạng thái cache, hãy ghi nhận trạng thái thực tế và lặp lại đủ lần để hiểu mức biến động.

## 6. Quy trình thiết lập đường cơ sở

Thực hiện theo trình tự sau để mỗi kết quả đều có bối cảnh và có thể so sánh:

1. **Chốt câu hỏi và giả thuyết.** Ghi rõ vấn đề, phạm vi, nhóm truy vấn, mục tiêu và chỉ số chứng minh.
2. **Chọn cửa sổ đại diện.** Bao gồm thời điểm có tải bình thường và tải cao nếu vấn đề xuất hiện ở cả hai. Ghi thời điểm bắt đầu/kết thúc và các tác vụ nền xảy ra trong cửa sổ.
3. **Kiểm tra dữ liệu và môi trường.** Xác nhận schema, số dòng, thống kê optimizer, phiên bản, cấu hình, phần cứng, cache và connection pool.
4. **Thu thập workload.** Ghi tỷ lệ loại thao tác, tham số đại diện, tần suất, mức đồng thời, batch size và kích thước kết quả.
5. **Lấy snapshot ban đầu.** Chụp các bộ đếm tích lũy và trạng thái tài nguyên trước cửa sổ đo; ghi thời điểm snapshot và thời điểm reset gần nhất nếu biết.
6. **Chạy hoặc quan sát workload.** Dùng tải đại diện, không thay đổi cấu hình giữa chừng. Tách warm-up khỏi khoảng ghi nhận nếu cần đo trạng thái ổn định.
7. **Lấy snapshot kết thúc.** Chụp lại cùng nhóm bộ đếm. Tính hiệu, tốc độ phát sinh và chi phí trên mỗi transaction.
8. **Thu thập kế hoạch thực thi.** Lấy execution plan của các câu lệnh trọng yếu với tham số đại diện; lưu số dòng ước lượng/thực tế, số vòng lặp, buffer, I/O và operator đáng chú ý.
9. **Tổng hợp và kiểm tra tính hợp lệ.** Đối chiếu số liệu ứng dụng, truy vấn và máy chủ; loại trừ cửa sổ bị nhiễu hoặc đánh dấu rõ sự kiện gây nhiễu.
10. **Lưu hồ sơ baseline.** Lưu dữ liệu thô, câu lệnh đo, thời gian, điều kiện, kết quả tổng hợp, giả thuyết và quyết định tiếp theo ở nơi có thể truy xuất.

Nếu số liệu cho thấy tải trong cửa sổ đo khác xa điều kiện mục tiêu, không nên ép so sánh bằng cách chỉ lấy một con số trung bình. Hãy chọn lại cửa sổ, chạy lại phép đo hoặc ghi rõ giới hạn của kết quả.

## 7. Thu thập số liệu bằng công cụ cơ sở dữ liệu

Các công cụ cụ thể phụ thuộc hệ quản trị và phiên bản. Ví dụ dưới đây minh họa PostgreSQL; cần kiểm tra phiên bản và quyền truy cập trước khi dùng trong môi trường thực tế.

### Thống kê câu lệnh với pg_stat_statements

Nếu extension `pg_stat_statements` đã được cài đặt và bật, có thể lấy danh sách các mẫu câu lệnh có tổng thời gian thực thi cao:

```sql
SELECT queryid,
       calls,
       total_exec_time,
       mean_exec_time,
       rows,
       shared_blks_hit,
       shared_blks_read,
       temp_blks_written
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
```

`calls` cho biết số lần gọi; `total_exec_time` giúp tìm nhóm câu lệnh đóng góp nhiều thời gian; `mean_exec_time` cho biết trung bình mỗi lần gọi. Các bộ đếm block và temporary giúp định hướng điều tra I/O và dữ liệu tạm. Thống kê này thường tích lũy từ lần reset hoặc thời điểm thu thập; cần ghi lại thời điểm và tính chênh lệch giữa hai snapshot để phân tích một cửa sổ cụ thể. Tên cột và cách thu thập có thể thay đổi theo phiên bản PostgreSQL.

### Thống kê cấp cơ sở dữ liệu

Có thể lấy snapshot một số bộ đếm ở `pg_stat_database`:

```sql
SELECT datname,
       numbackends,
       xact_commit,
       xact_rollback,
       blks_read,
       blks_hit,
       tup_returned,
       tup_fetched,
       temp_files,
       temp_bytes,
       deadlocks,
       stats_reset
FROM pg_stat_database
WHERE datname = current_database();
```

Lưu kết quả ở đầu và cuối cửa sổ đo, sau đó tính hiệu cho các bộ đếm tích lũy như commit, rollback, block đọc, block hit, dữ liệu tạm và deadlock. `numbackends` là số backend tại thời điểm lấy mẫu, không phải bộ đếm tích lũy. `stats_reset` giúp nhận biết thời điểm reset thống kê; nếu bộ đếm bị reset giữa hai snapshot thì phép trừ đơn giản không còn hợp lệ.

### Xem kế hoạch và số liệu thực thi

Với truy vấn trọng yếu, lưu kế hoạch thực thi và số liệu thực tế. PostgreSQL hỗ trợ:

```sql
EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 4201
  AND status = 'PAID'
ORDER BY created_at DESC
LIMIT 50;
```

Đối chiếu `rows` ước lượng với `actual rows`, `loops`, thời gian tại từng nút và buffer hit/read. Chênh lệch lớn giữa ước lượng và thực tế có thể cho thấy thống kê optimizer không phản ánh đúng phân bố dữ liệu. Số vòng lặp lớn có thể khiến một nút nhỏ trở thành chi phí đáng kể. Buffer read cao có thể chỉ ra nhiều trang phải đưa vào shared buffers; không mặc định mọi lần đọc này đều là I/O vật lý trên thiết bị.

`EXPLAIN ANALYZE` thực thi câu lệnh. Với câu lệnh ghi, trigger hoặc hàm có tác động phụ, chỉ chạy trong môi trường thử nghiệm hoặc quy trình đã kiểm soát. Cần dùng tham số đại diện và lưu đúng câu lệnh cùng tham số để có thể so sánh lần sau.

### Theo dõi trạng thái đang hoạt động

`pg_stat_activity` giúp quan sát session đang hoạt động và wait event tại thời điểm lấy mẫu:

```sql
SELECT pid,
       state,
       wait_event_type,
       wait_event,
       clock_timestamp() - query_start AS elapsed,
       LEFT(query, 160) AS query_sample
FROM pg_stat_activity
WHERE state = 'active'
ORDER BY query_start;
```

Đây là ảnh chụp trạng thái hiện tại, không phải lịch sử đầy đủ của một câu lệnh. Muốn biết thời gian chờ tích lũy hoặc phân bố wait event, cần lấy mẫu có chu kỳ hoặc dùng hệ thống giám sát lưu lịch sử. Tránh ghi log nội dung truy vấn có thể chứa dữ liệu nhạy cảm; áp dụng quyền truy cập và chính sách ẩn danh phù hợp.

### Đối chiếu các hệ quản trị khác

| Hệ quản trị | Công cụ thường dùng để lập baseline | Nội dung có thể thu thập |
|---|---|---|
| MySQL | Performance Schema, `sys` schema, slow query log, `EXPLAIN ANALYZE` ở phiên bản hỗ trợ | Thời gian statement, số dòng, wait, sort, bảng tạm, I/O và kế hoạch |
| SQL Server | Query Store, execution plan, `SET STATISTICS TIME`, `SET STATISTICS IO`, wait statistics | CPU/elapsed, logical reads, kế hoạch theo thời gian, wait và mức sử dụng tài nguyên |
| Oracle Database | AWR/ASH khi được cấp phép và cấu hình phù hợp, `V$SQL`, session wait events, SQL Trace | CPU/elapsed, số lần thực thi, buffer gets, I/O, wait event và kế hoạch |

Tên trường, quyền cần thiết, phạm vi dữ liệu lưu giữ và điều kiện cấp phép khác nhau. Hãy sử dụng công cụ được hỗ trợ trong môi trường của tổ chức và kiểm tra tài liệu đúng phiên bản.

## 8. Thiết kế phép đo lặp lại và có thể so sánh

### Giữ điều kiện tương đương

Để so sánh trước/sau, hãy cố định hoặc ghi lại các yếu tố có thể ảnh hưởng kết quả:

- Cùng phiên bản ứng dụng, câu lệnh, tham số và cách bind tham số.
- Cùng bộ dữ liệu hoặc dữ liệu có quy mô, phân bố và độ mới tương đương.
- Cùng cấu hình phần cứng, database, storage, connection pool và mức đồng thời.
- Cùng cách đo, đơn vị, vị trí bắt đầu/kết thúc và thời lượng cửa sổ.
- Cùng trạng thái cache hoặc cùng quy trình warm-up.
- Cùng tác vụ nền, hoặc ghi rõ tác vụ nền khác biệt và mức ảnh hưởng.

Trong thực tế, không phải lúc nào cũng giữ được tất cả yếu tố cố định. Khi đó, cần ghi rõ sai khác và tránh quy kết toàn bộ chênh lệch cho thay đổi vừa thực hiện.

### Chạy đủ lần và tách warm-up

Một lần chạy đơn lẻ dễ bị ảnh hưởng bởi cache, lịch CPU, checkpoint, backup, hoạt động vacuum hoặc tải từ session khác. Hãy chạy warm-up nếu mục tiêu là trạng thái ổn định, sau đó thu thập nhiều lần hoặc một cửa sổ đủ dài. Báo cáo số mẫu, phân vị, độ biến động và các lần chạy bất thường.

Nếu cần đánh giá cache lạnh, hãy tách thành kịch bản riêng. Không gộp kết quả cache lạnh và cache nóng vào một trung bình chung vì hai trạng thái mô tả hành vi khác nhau.

### Tái hiện mức đồng thời

Khi hệ thống thực tế có nhiều request cùng chạy, phép thử một kết nối không thể hiện đầy đủ lock contention, hàng đợi CPU, giới hạn connection pool hoặc áp lực I/O. Hãy tăng tải theo các mức có kiểm soát, ví dụ tải thấp, tải thông thường và tải đỉnh dự kiến. Ở mỗi mức, đo throughput, p95/p99, lỗi, CPU, wait event và số kết nối.

Phải phân biệt cách tạo tải:

- **Mô hình đóng (closed-loop):** mỗi worker gửi yêu cầu tiếp theo sau khi yêu cầu trước hoàn thành. Khi hệ thống chậm, tốc độ phát sinh yêu cầu cũng tự giảm.
- **Mô hình mở (open-loop):** yêu cầu được phát sinh theo tốc độ định trước, gần với hệ thống có lưu lượng đến độc lập với thời gian xử lý. Khi năng lực phục vụ không đủ, hàng đợi và độ trễ có thể tăng.

Chọn mô hình phù hợp với hành vi thực tế. Một bài thử closed-loop có thể che giấu việc hệ thống không đáp ứng được tốc độ yêu cầu đầu vào nếu không theo dõi số request bị xếp hàng hoặc không được phát sinh.

## 9. Ví dụ lập hồ sơ baseline

Giả sử nhóm vận hành cần cải thiện API tra cứu đơn hàng. Trong cửa sổ 30 phút ở giờ cao điểm, nhóm thu được số liệu minh họa sau:

| Chỉ số | Đường cơ sở |
|---|---:|
| Request hoàn thành | 180.000 |
| Throughput trung bình | 100 request/giây |
| Độ trễ p50 | 42 ms |
| Độ trễ p95 | 310 ms |
| Độ trễ p99 | 820 ms |
| Tỷ lệ lỗi/timeout | 0,25% |
| CPU máy chủ trung bình | 68% |
| Logical reads trung bình mỗi lần gọi | 1.850 |
| Số lần gọi truy vấn chính | 180.000 |

Execution plan cho nhóm tham số khách hàng có nhiều đơn cho thấy hệ quản trị đọc một tập dòng lớn rồi lọc theo trạng thái và sắp xếp theo thời gian. Số dòng thực tế cao hơn nhiều so với nhóm khách hàng ít đơn. Nhóm ghi nhận schema, chỉ mục hiện có, thống kê optimizer, kích thước bảng, cấu hình máy chủ, trạng thái cache và mức đồng thời cùng thời điểm đo.

Từ dữ liệu này, nhóm đưa ra giả thuyết rằng truy vấn phải đọc quá nhiều dòng đối với khách hàng có lịch sử lớn. Mục tiêu thử nghiệm được xác định là giảm p95 và logical reads mỗi lần gọi, trong khi throughput không giảm, tỷ lệ lỗi không tăng và CPU/chi phí ghi không vượt giới hạn đã thống nhất.

Đường cơ sở cũng cho thấy không nên chỉ so sánh thời gian của một lần gọi. Sau khi điều chỉnh, nhóm cần chạy lại cùng nhóm tham số, cùng dữ liệu và mức tải tương đương; đo đủ lâu; kiểm tra p50/p95/p99, throughput, lỗi, logical reads, CPU và chi phí ghi. Nếu p95 giảm nhưng p99 tăng mạnh hoặc thao tác ghi suy giảm đáng kể, kết quả chưa đáp ứng mục tiêu tổng thể.

Các con số trên chỉ minh họa cách lập hồ sơ, không phải ngưỡng chuẩn cho mọi hệ thống. SLO phải được xác định theo yêu cầu nghiệp vụ và năng lực hạ tầng cụ thể.

## 10. Mẫu ghi nhận đường cơ sở

Có thể dùng mẫu sau trong ticket tối ưu, tài liệu vận hành hoặc hồ sơ thay đổi:

| Trường | Nội dung cần điền |
|---|---|
| Mã vấn đề / chức năng | Tên ticket, API hoặc transaction |
| Mục tiêu đo | Triệu chứng và kết quả mong muốn |
| Giả thuyết | Nguyên nhân dự kiến và dấu hiệu kiểm chứng |
| Câu lệnh / query fingerprint | Query ID, mẫu SQL đã loại dữ liệu nhạy cảm và tham số đại diện |
| Khoảng đo | Ngày giờ, múi giờ, thời lượng và số mẫu |
| Workload | Throughput, mức đồng thời, tỷ lệ đọc/ghi, nhóm tham số |
| Môi trường | DB version, phần cứng, storage, cấu hình, schema và phiên bản ứng dụng |
| Trạng thái dữ liệu | Số dòng, kích thước, thống kê optimizer và trạng thái cache |
| Kết quả độ trễ | p50, p95, p99, mean và tỷ lệ vượt SLO |
| Kết quả tài nguyên | CPU, memory, I/O, wait, logical reads, temp, lock/deadlock |
| Kế hoạch thực thi | Execution plan, actual rows, estimated rows, loops và operator chính |
| Sự kiện gây nhiễu | Backup, batch, deploy, checkpoint hoặc tải nền bất thường |
| Quyết định | Có đủ dữ liệu để thử thay đổi hay cần đo lại |

Lưu cả số liệu thô và kết quả tổng hợp. Không chỉ lưu ảnh chụp màn hình vì ảnh có thể thiếu đơn vị, bộ lọc hoặc mốc thời gian. Đảm bảo hồ sơ có thể truy xuất và không làm lộ SQL chứa thông tin cá nhân, token hoặc dữ liệu bí mật.

## 11. Dùng đường cơ sở để đánh giá thay đổi

Khi baseline đã đủ tin cậy, thực hiện thay đổi theo một chu trình có kiểm soát:

1. Ghi cấu hình và trạng thái trước thay đổi; xác nhận baseline đã hoàn tất.
2. Chỉ thay đổi một nhóm yếu tố có quan hệ rõ với giả thuyết, chẳng hạn chỉ mục hoặc một tham số cấu hình.
3. Ghi lại chính xác nội dung thay đổi, người thực hiện, thời điểm và kế hoạch hoàn tác.
4. Chạy cùng workload và điều kiện đo; tách giai đoạn warm-up nếu cần.
5. So sánh các chỉ số chính và chỉ số bảo vệ: độ trễ, throughput, lỗi, CPU, I/O, bộ nhớ, khóa và chi phí ghi.
6. Kiểm tra các workload liên quan để phát hiện tác động phụ, ví dụ chỉ mục mới làm tăng thời gian INSERT/UPDATE hoặc tăng dung lượng lưu trữ.
7. Chấp nhận thay đổi khi kết quả lặp lại được và đạt mục tiêu; nếu kết quả không ổn định hoặc vi phạm giới hạn, tiếp tục điều tra hay hoàn tác theo kế hoạch.

Nên so sánh theo cả giá trị tuyệt đối và mức thay đổi tương đối. Ví dụ, giảm p95 từ 400 ms xuống 300 ms là giảm 25%; nhưng nếu cùng lúc throughput giảm 30% thì chưa thể coi đó là cải thiện. Cần xem cả phân bố kết quả và các workload cùng chia sẻ tài nguyên.

Không dùng baseline cũ vô thời hạn. Khi dữ liệu tăng trưởng, phiên bản phần mềm thay đổi, phần cứng được nâng cấp, workload chuyển dịch hoặc cấu hình nền tảng thay đổi, cần thiết lập baseline mới hoặc ít nhất ghi nhận mốc mới để so sánh công bằng.

## 12. Những lỗi thường gặp khi lập baseline

- **Chỉ đo một lần:** kết quả có thể là ngoại lệ do cache, lịch CPU hoặc tải nền.
- **Chỉ dùng mean:** đuôi phân phối chậm bị che khuất, trong khi người dùng vẫn gặp timeout.
- **Chỉ chạy truy vấn đơn lẻ:** bỏ qua contention, connection pool, I/O và hàng đợi khi tải đồng thời.
- **Không lưu tham số truy vấn:** cùng một SQL có thể có kế hoạch hoặc số dòng khác nhau tùy giá trị tham số.
- **Không ghi trạng thái cache:** so sánh lần chạy nóng với lần chạy lạnh dẫn tới kết luận sai.
- **Đọc bộ đếm tích lũy như số liệu trong cửa sổ:** không lấy snapshot đầu/cuối hoặc không kiểm tra thời điểm reset.
- **Đo ứng dụng và máy chủ bằng hai phạm vi khác nhau:** không thể giải thích phần chênh lệch thời gian.
- **Bỏ qua tác vụ nền:** backup, batch, checkpoint hoặc bảo trì có thể làm sai lệch số liệu.
- **Chỉ nhìn truy vấn mục tiêu:** thay đổi có thể làm workload khác chậm hơn hoặc tăng chi phí ghi.
- **Không lưu execution plan:** thiếu căn cứ để giải thích số liệu thay đổi do đâu.
- **Thay nhiều yếu tố cùng lúc:** khó xác định thay đổi nào tạo ra kết quả và khó hoàn tác an toàn.
- **Đặt mục tiêu không gắn với nghiệp vụ:** một con số thấp hơn không nhất thiết cải thiện trải nghiệm hoặc năng lực phục vụ.

## 13. Checklist trước khi bắt đầu tối ưu

- [ ] Đã xác định truy vấn, transaction hoặc hành trình nghiệp vụ cần cải thiện.
- [ ] Đã ghi giả thuyết và chỉ số sẽ dùng để kiểm chứng.
- [ ] Workload có mức đồng thời, tần suất, tỷ lệ đọc/ghi và tham số đại diện.
- [ ] Dữ liệu thử nghiệm phản ánh quy mô và phân bố dữ liệu cần tối ưu.
- [ ] Đã ghi phiên bản DB, phần cứng, storage, cấu hình, schema và trạng thái thống kê.
- [ ] Đã xác định rõ phạm vi và ranh giới đo ở ứng dụng và cơ sở dữ liệu.
- [ ] Có p50/p95/p99, throughput, tỷ lệ lỗi và số lượng mẫu.
- [ ] Có số liệu CPU, I/O, bộ nhớ, wait, lock và dữ liệu tạm phù hợp với vấn đề.
- [ ] Đã lưu execution plan và số liệu thực tế của truy vấn trọng yếu.
- [ ] Đã ghi snapshot đầu/cuối cho các bộ đếm tích lũy và kiểm tra thời điểm reset.
- [ ] Đã tách warm-up khỏi cửa sổ đo khi mục tiêu yêu cầu trạng thái ổn định.
- [ ] Đã lưu số liệu thô, điều kiện đo, sự kiện gây nhiễu và quyết định tiếp theo.

Đường cơ sở tốt giúp biến tối ưu hiệu năng từ hoạt động thử và đoán thành một quy trình có thể kiểm chứng. Khi workload, điều kiện môi trường, số liệu và giả thuyết được ghi lại đầy đủ, nhóm có thể xác định đúng điểm nghẽn, đánh giá tác động của thay đổi và duy trì hiệu năng ổn định khi tải hoặc dữ liệu tiếp tục tăng.
