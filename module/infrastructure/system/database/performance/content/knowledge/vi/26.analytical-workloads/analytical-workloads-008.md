# Đánh đổi độ tươi dữ liệu, thời gian phản hồi và chi phí tính toán

Một hệ thống phân tích thường phải trả lời ba câu hỏi cùng lúc: dữ liệu mới đến mức nào, người dùng phải chờ bao lâu để nhận kết quả và hệ thống tiêu tốn bao nhiêu tài nguyên để tạo ra kết quả đó. Ba mục tiêu này liên quan chặt chẽ với nhau. Truy vấn trực tiếp trên dữ liệu nguồn có thể phản ánh thay đổi mới nhất nhưng tốn thời gian và tài nguyên. Tính toán trước hoặc lưu kết quả vào cache có thể trả lời rất nhanh và giảm tải truy vấn, nhưng dữ liệu hiển thị có thể cũ hơn. Chạy pipeline thường xuyên hơn làm giảm độ trễ dữ liệu, đồng thời tăng chi phí tính toán, I/O và vận hành.

Trong chương **Tải phân tích** của module **DATABASE_PERFORMANCE**, bài học này trình bày cách lựa chọn điểm cân bằng giữa độ tươi dữ liệu, thời gian phản hồi và chi phí tính toán. Module **DATABASE_PERFORMANCE** rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; nội dung bao gồm thiết kế chỉ mục, cải thiện SQL, nhận diện tranh chấp giao dịch, nút thắt I/O, bộ nhớ và kiểm chứng sau điều chỉnh. Vì vậy, tối ưu workload phân tích phải đo cả pipeline tạo dữ liệu, thời gian truy vấn, mức tài nguyên, độ chính xác và tác động lên workload giao dịch.

## 1. Ba mục tiêu cần đánh đổi

### 1.1. Độ tươi dữ liệu (data freshness)

Độ tươi mô tả khoảng cách giữa thời điểm dữ liệu phát sinh và thời điểm dữ liệu đó có thể được truy vấn trong hệ thống phân tích. Cần phân biệt các mốc:

- **Event time:** thời điểm sự kiện thực sự xảy ra trong nghiệp vụ.
- **Ingestion time:** thời điểm dữ liệu được nhận vào hệ thống.
- **Processing time:** thời điểm pipeline xử lý dữ liệu.
- **Publication time:** thời điểm kết quả đã sẵn sàng cho người dùng hoặc truy vấn.

Một sự kiện xảy ra lúc 10:00 nhưng chỉ được gửi đến hệ thống lúc 10:04, xử lý xong lúc 10:06 và công bố lúc 10:07 có độ trễ công bố so với event time là 7 phút. Nếu chỉ đo từ ingestion time, hệ thống có thể báo độ trễ 3 phút và che khuất việc nguồn gửi dữ liệu muộn.

Cần định nghĩa freshness theo mục tiêu nghiệp vụ. Dashboard vận hành có thể yêu cầu dữ liệu mới trong vài phút; báo cáo doanh thu cuối ngày có thể chấp nhận độ trễ nhiều giờ; báo cáo tài chính đã đối soát có thể ưu tiên tính đầy đủ và ổn định hơn dữ liệu tức thời.

### 1.2. Thời gian phản hồi (query response latency)

Latency là thời gian từ lúc người dùng hoặc ứng dụng gửi yêu cầu đến khi nhận được kết quả. Cần đo các phân vị:

- p50 mô tả trải nghiệm điển hình.
- p95 phản ánh nhóm yêu cầu chậm hơn đáng kể.
- p99 cho thấy đuôi độ trễ và các trường hợp hiếm nhưng ảnh hưởng lớn.

Một truy vấn trung bình 300 ms nhưng p99 là 20 giây có thể vẫn gây trải nghiệm kém. Với workload phân tích, latency còn phụ thuộc kích thước dữ liệu được quét, concurrency, cache, số phép nối, tổng hợp, spill và khả năng song song.

### 1.3. Chi phí tính toán (compute cost)

Chi phí không chỉ là CPU. Cần tính cả:

- CPU time và số core được sử dụng.
- Bộ nhớ và memory grant.
- I/O đọc dữ liệu nguồn và ghi dữ liệu trung gian.
- Dung lượng lưu trữ cho bản tổng hợp, snapshot và cache.
- Network transfer giữa hệ thống nguồn, pipeline và nơi phục vụ.
- Chi phí làm mới, backfill, retry và vận hành.
- Tài nguyên bị chiếm dụng khiến workload khác phải chờ.

Một giải pháp trả lời nhanh hơn có thể tốn thêm chi phí refresh hoặc lưu trữ. Một giải pháp rẻ hơn có thể làm dữ liệu cũ hơn hoặc tăng thời gian người dùng chờ. Cần đánh giá trên cùng một đơn vị nghiệp vụ, chẳng hạn chi phí cho mỗi triệu sự kiện được xử lý hoặc mỗi nghìn truy vấn dashboard.

## 2. Định nghĩa SLO cho từng loại phân tích

Không nên đặt một mục tiêu freshness và latency duy nhất cho mọi báo cáo. Hãy phân nhóm theo mức độ quan trọng và hành vi sử dụng.

| Loại workload | Freshness có thể chấp nhận | Latency mục tiêu | Ưu tiên chính |
|---|---|---|---|
| Dashboard vận hành trực tiếp | Vài giây đến vài phút | Thấp, thường dưới vài giây | Phát hiện sự cố nhanh |
| Theo dõi đơn hàng và tồn kho | Vài phút | Thấp đến trung bình | Hành động nghiệp vụ kịp thời |
| Dashboard quản trị | 5–30 phút hoặc theo lịch | Vài giây | Ổn định và dễ sử dụng |
| Báo cáo ngày | Theo giờ hoặc sau khi chốt ngày | Vài giây đến vài phút | Đầy đủ và nhất quán |
| Phân tích lịch sử chuyên sâu | Có thể theo batch | Vài phút hoặc lâu hơn | Độ sâu và chi phí hợp lý |
| Đối soát tài chính | Theo chu kỳ đã xác nhận | Không nhất thiết tức thời | Chính xác, truy vết được |

Các khoảng thời gian trên chỉ là ví dụ. SLO phải xuất phát từ quyết định mà người dùng cần đưa ra. Nếu dashboard chỉ được xem mỗi giờ, việc làm mới mỗi giây có thể không tạo giá trị tương xứng với chi phí. Nếu hệ thống phát hiện gian lận cần phản ứng trong vài giây, batch chạy mỗi 15 phút là không phù hợp.

Một SLO tốt cần định nghĩa rõ:

- Freshness được đo từ event time, ingestion time hay nguồn khác.
- Tỷ lệ dữ liệu phải đạt freshness mục tiêu.
- Latency p95/p99 và kích thước truy vấn đại diện.
- Mức độ đầy đủ, sai số hoặc độ trễ chấp nhận được.
- Khoảng thời gian và tải dùng để đánh giá.
- Hành vi khi pipeline trễ hoặc dữ liệu nguồn không sẵn sàng.

## 3. Đo freshness thay vì chỉ xem thời điểm refresh

Một bảng tổng hợp có cột refreshed_at mới không chứng minh mọi dữ liệu nguồn đã được xử lý đầy đủ. Pipeline có thể vừa chạy xong nhưng bỏ sót một partition, một shard hoặc các sự kiện đến muộn.

Nên theo dõi ít nhất:

- Thời điểm event time mới nhất đã được xử lý.
- Thời điểm ingestion mới nhất đã được nhận.
- Thời điểm xử lý và công bố thành công.
- Số lượng sự kiện nhận vào, xử lý, loại bỏ và đang chờ.
- Watermark hoặc checkpoint hiện tại.
- Độ trễ theo từng partition, tenant hoặc nguồn dữ liệu.
- Số sự kiện đến muộn và số lần backfill/correction.

Ví dụ, nếu dashboard tổng hợp doanh thu theo phút, có thể công bố trường data_through = 10:00 để nói rõ kết quả hiện bao phủ sự kiện đến thời điểm nào. Người dùng sẽ hiểu rằng thời gian cập nhật giao diện lúc 10:07 không có nghĩa dữ liệu đến 10:07 đã được tính.

## 4. Truy vấn trực tiếp trên dữ liệu nguồn

Cách đơn giản nhất là tính kết quả tại thời điểm người dùng yêu cầu. Mỗi truy vấn đọc các bảng nguồn, áp dụng filter, join, aggregate rồi trả kết quả.

Ưu điểm:

- Dữ liệu có thể gần với trạng thái mới nhất.
- Không cần lưu nhiều bản tổng hợp trùng lặp.
- Không cần pipeline refresh riêng cho từng metric.
- Logic tính toán có thể dùng cùng dữ liệu giao dịch hiện tại theo isolation phù hợp.

Giới hạn:

- Truy vấn phức tạp có thể quét nhiều dữ liệu.
- Nhiều người dùng cùng mở dashboard có thể lặp lại cùng phép tính.
- CPU, I/O và memory grant tăng theo concurrency.
- Một truy vấn nặng có thể ảnh hưởng workload OLTP.
- Latency phụ thuộc kích thước bảng và phân bố dữ liệu.

Ví dụ:

~~~sql
SELECT
    date_trunc('hour', created_at) AS hour_bucket,
    COUNT(*) AS order_count,
    SUM(total_amount) AS revenue
FROM orders
WHERE created_at >= :start_time
  AND created_at < :end_time
  AND status = 'COMPLETED'
GROUP BY date_trunc('hour', created_at)
ORDER BY hour_bucket;
~~~

Truy vấn trực tiếp có thể phù hợp khi phạm vi thời gian nhỏ, dữ liệu vừa phải, tần suất truy cập thấp hoặc freshness là yêu cầu quan trọng nhất. Nếu dashboard được gọi hàng trăm lần mỗi phút với cùng tham số, tính lại cùng một aggregate có thể lãng phí.

## 5. Batch processing: giảm chi phí bằng cách chấp nhận độ trễ

Batch processing gom dữ liệu theo khoảng thời gian hoặc số lượng rồi xử lý một lần. Ví dụ, mỗi 15 phút pipeline đọc các sự kiện mới, cập nhật bảng tổng hợp và công bố kết quả.

Lợi ích:

- Tận dụng đọc tuần tự và xử lý theo khối.
- Giảm overhead khởi chạy tác vụ nhỏ liên tục.
- Dễ kiểm soát checkpoint, retry và đối soát.
- Có thể dùng bulk load hoặc thao tác set-based.
- Chi phí vận hành thường dễ dự đoán.

Đổi lại, dữ liệu mới có thể phải chờ đến chu kỳ tiếp theo. Nếu batch chạy 15 phút một lần và mất 4 phút, độ trễ công bố có thể gần 19 phút ở trường hợp xấu, chưa kể dữ liệu nguồn đến muộn hoặc pipeline retry.

Batch phù hợp với báo cáo ngày, tổng hợp lịch sử, dữ liệu không cần phản ứng tức thời và workload có thể lên lịch theo cửa sổ tải thấp.

## 6. Micro-batch: cân bằng độ trễ và overhead

Micro-batch chia dữ liệu thành các lô nhỏ, xử lý theo chu kỳ ngắn hơn, chẳng hạn 10 giây, 1 phút hoặc 5 phút. Nó thường là lựa chọn trung gian giữa batch lớn và xử lý streaming liên tục.

Ưu điểm:

- Freshness tốt hơn batch dài.
- Có thể dùng lại logic xử lý theo lô.
- Dễ quản lý transaction và checkpoint hơn một số pipeline streaming.
- Có thể gom nhiều sự kiện để giảm overhead từng record.

Nhược điểm:

- Chu kỳ càng ngắn, overhead khởi chạy và commit càng thường xuyên.
- Nhiều batch nhỏ có thể tạo nhiều lần đọc/ghi và cập nhật index.
- Nếu mỗi batch mất lâu hơn chu kỳ, backlog tăng liên tục.
- Cần xử lý batch trùng lặp và retry an toàn.

Một pipeline chạy mỗi phút nhưng mỗi batch mất 90 giây không thể giữ freshness ổn định. Cần đo thời gian xử lý, thời gian chờ, kích thước backlog và tốc độ dữ liệu đầu vào, không chỉ nhìn cấu hình lịch chạy.

## 7. Streaming: freshness thấp với chi phí vận hành cao hơn

Streaming xử lý sự kiện liên tục hoặc theo luồng nhỏ, thường sử dụng message broker, log-based CDC hoặc nền tảng stream processing. Kết quả có thể được cập nhật trong vài giây hoặc ngắn hơn tùy hệ thống.

Lợi ích:

- Giảm thời gian từ event đến kết quả phân tích.
- Phù hợp phát hiện bất thường, giám sát vận hành và quyết định nhanh.
- Có thể duy trì aggregate tăng dần thay vì quét lại toàn bộ dữ liệu.
- Tách workload đọc phân tích khỏi hệ thống giao dịch nếu thiết kế đúng.

Đổi lại:

- Cần quản lý offset, checkpoint, watermark và backpressure.
- Sự kiện trùng lặp hoặc đến sai thứ tự phải được xử lý.
- Late-arriving events có thể yêu cầu cập nhật kết quả đã công bố.
- Hệ thống cần giám sát liên tục và xử lý lỗi phân tán.
- Chi phí hạ tầng, vận hành và kỹ năng có thể cao hơn batch.

Streaming không mặc nhiên bảo đảm dữ liệu chính xác tức thời. Một pipeline có thể xử lý nhanh nhưng chưa nhận đủ sự kiện do nguồn phát chậm hoặc watermark chưa tiến. Freshness và completeness phải được đo riêng.
## 8. Tính toán trước bằng bảng tổng hợp hoặc materialized view

Nếu nhiều truy vấn lặp lại cùng phép tổng hợp, có thể tính trước kết quả rồi phục vụ dashboard từ bảng tổng hợp hoặc materialized view.

Ví dụ:

~~~sql
CREATE MATERIALIZED VIEW hourly_order_metrics AS
SELECT
    date_trunc('hour', created_at) AS hour_bucket,
    tenant_id,
    COUNT(*) AS order_count,
    SUM(total_amount) AS revenue
FROM orders
WHERE status = 'COMPLETED'
GROUP BY date_trunc('hour', created_at), tenant_id;
~~~

Truy vấn dashboard sau đó đọc số hàng đã tổng hợp:

~~~sql
SELECT hour_bucket, order_count, revenue
FROM hourly_order_metrics
WHERE tenant_id = :tenant_id
  AND hour_bucket >= :start_hour
  AND hour_bucket < :end_hour
ORDER BY hour_bucket;
~~~

Lợi ích là giảm lượng dữ liệu cần quét và tính toán mỗi lần người dùng mở dashboard. Chi phí chuyển sang giai đoạn refresh: hệ thống phải tạo, cập nhật và lưu kết quả.

Cần chú ý semantics của materialized view khác nhau theo database. PostgreSQL có REFRESH MATERIALIZED VIEW, nhưng cơ chế refresh chuẩn của nó tính lại nội dung view; tùy chọn CONCURRENTLY thay đổi cách phục vụ đọc và có điều kiện riêng, không biến refresh thành incremental tự động. Một số hệ quản trị hoặc nền tảng kho dữ liệu có incremental materialized view với giới hạn riêng. Hãy kiểm tra tài liệu engine và phiên bản.

## 9. Refresh toàn bộ hay cập nhật tăng dần?

Có hai hướng chính:

**Full refresh:** tính lại toàn bộ kết quả từ dữ liệu nguồn. Cách này đơn giản và có thể khôi phục kết quả chuẩn từ đầu, nhưng chi phí tăng theo kích thước lịch sử.

**Incremental refresh:** chỉ xử lý phần dữ liệu mới hoặc phần bị thay đổi. Cách này giảm công việc nếu dữ liệu đến theo thứ tự và có thể xác định chính xác phần cần cập nhật. Đổi lại, logic phức tạp hơn khi có UPDATE, DELETE, late event hoặc dữ liệu cần sửa lại.

Ví dụ bảng tổng hợp theo giờ có thể cập nhật bằng UPSERT theo khóa (tenant_id, hour_bucket):

~~~sql
INSERT INTO hourly_order_metrics (
    tenant_id,
    hour_bucket,
    order_count,
    revenue
)
SELECT
    tenant_id,
    date_trunc('hour', created_at),
    COUNT(*),
    SUM(total_amount)
FROM orders
WHERE created_at >= :window_start
  AND created_at < :window_end
  AND status = 'COMPLETED'
GROUP BY tenant_id, date_trunc('hour', created_at)
ON CONFLICT (tenant_id, hour_bucket)
DO UPDATE SET
    order_count = EXCLUDED.order_count,
    revenue = EXCLUDED.revenue;
~~~

Ví dụ trên tính lại toàn bộ bucket trong cửa sổ rồi thay thế aggregate của bucket đó. Nó không phải phép cộng dồn mù vào giá trị cũ. Cách này an toàn hơn khi chạy lại cùng cửa sổ, miễn là nguồn dữ liệu và quy tắc transaction nhất quán.

Nếu chỉ cộng thêm delta mà không có idempotency, retry có thể đếm trùng. Nếu có UPDATE/DELETE trên dữ liệu nguồn, cần phát hiện thay đổi và điều chỉnh aggregate tương ứng.

## 10. Late-arriving data và watermark

Sự kiện có thể đến sau thời điểm xảy ra do mạng, thiết bị offline, retry hoặc nguồn dữ liệu xử lý chậm. Nếu pipeline chỉ xử lý các sự kiện mới hơn watermark và bỏ qua dữ liệu đến muộn, kết quả phân tích sẽ thiếu.

Watermark là mốc mà pipeline dùng để ước lượng rằng phần lớn sự kiện trước một thời điểm đã đến. Watermark không nhất thiết chứng minh sẽ không còn sự kiện cũ hơn xuất hiện.

Cần xác định:

- Cho phép sự kiện đến muộn tối đa bao lâu?
- Có cập nhật lại bucket đã công bố không?
- Có cửa sổ correction/backfill không?
- Sau bao lâu thì kết quả được xem là đã chốt?
- Người dùng nhìn thấy trạng thái provisional hay finalized?
- Sự kiện đến quá muộn được ghi nhận, loại bỏ hay xử lý riêng?

Ví dụ, dashboard hiển thị doanh thu theo phút có thể công bố số liệu tạm thời sau 1 phút và điều chỉnh trong 30 phút tiếp theo. Báo cáo cuối ngày chỉ được chốt sau cửa sổ late-arrival và đối soát. Việc thể hiện rõ trạng thái giúp người dùng hiểu số liệu có thể thay đổi.

## 11. Consistency giữa dữ liệu nguồn và kết quả phân tích

Một kết quả tổng hợp có thể được tạo từ snapshot nguồn tại một thời điểm, trong khi bảng nguồn tiếp tục thay đổi. Cần xác định mức nhất quán mà báo cáo yêu cầu.

Một số lựa chọn:

- **Snapshot-consistent:** một lần chạy đọc một snapshot nhất quán của nguồn theo isolation level phù hợp.
- **Eventually consistent:** kết quả cập nhật sau một khoảng trễ và có thể tạm thời khác dữ liệu giao dịch mới nhất.
- **Bounded staleness:** chấp nhận dữ liệu cũ tối đa một khoảng được định nghĩa.
- **Finalized reporting:** dữ liệu được đối soát và chốt sau khi hết cửa sổ điều chỉnh.

Không nên gọi mọi pipeline có độ trễ là eventual consistency mà không nêu giới hạn. Hãy định nghĩa độ trễ tối đa, hành vi khi pipeline lỗi và cách sửa số liệu sau khi công bố.

Nếu dữ liệu nguồn được đọc qua nhiều transaction, các phần của aggregate có thể đến từ các snapshot khác nhau. Với báo cáo cần đối soát, cần dùng snapshot hoặc watermark nhất quán, batch ID và quy trình publish nguyên tử để tránh hiển thị kết quả nửa cũ nửa mới.

## 12. Cache: giảm latency nhưng phải quản lý stale data

Cache lưu kết quả đã tính để phục vụ yêu cầu lặp lại nhanh hơn. Cache có thể đặt ở ứng dụng, distributed cache, database cache hoặc tầng BI.

Các câu hỏi quan trọng:

- Cache key gồm tenant, filter, time range và quyền truy cập nào?
- TTL bao lâu?
- Cache được invalidated khi dữ liệu nguồn thay đổi hay refresh theo lịch?
- Có cho phép stale-while-revalidate không?
- Cache miss có làm nhiều request cùng tính lại một kết quả không?
- Có giới hạn kích thước và chính sách eviction không?

TTL ngắn giúp dữ liệu mới hơn nhưng tăng số lần tính lại. TTL dài giảm compute nhưng làm stale window lớn hơn. Cache stampede xảy ra khi nhiều request cùng miss một key và đồng thời thực hiện truy vấn đắt; có thể dùng request coalescing, single-flight, refresh nền hoặc khóa có thời hạn.

Không dùng cache để che một truy vấn sai hoặc thiếu index mà chưa đo. Cache hit cao có thể làm latency trung bình đẹp nhưng cache miss vẫn rất chậm; theo dõi cả hit ratio và latency của miss.

## 13. Tối ưu truy vấn trước khi tăng tần suất refresh

Tăng tần suất refresh có thể làm tổng compute tăng nhanh nếu mỗi lần chạy quét lại toàn bộ lịch sử. Trước khi giảm chu kỳ, hãy giảm chi phí mỗi lần chạy:

- Lọc theo khoảng thời gian có thể dùng index hoặc partition pruning.
- Chỉ đọc các cột cần thiết.
- Tính aggregate theo đúng grain.
- Tránh JOIN tạo fan-out không cần thiết.
- Dùng incremental processing khi có thể xác định delta chính xác.
- Thu thập và cập nhật statistics phù hợp.
- Kiểm tra execution plan, actual rows, buffers và spill.
- Tách truy vấn interactive khỏi truy vấn backfill lớn.

Ví dụ, nếu mỗi lần refresh đọc 3 năm dữ liệu để cập nhật một bucket mới, thiết kế có thể đang làm lại quá nhiều công việc. Có thể chỉ xử lý partition hoặc cửa sổ thay đổi, nhưng phải tính đến late data và correction.

## 14. Workload isolation: tránh để phân tích làm chậm giao dịch

Truy vấn phân tích thường đọc nhiều hàng, dùng CPU, memory và I/O lâu hơn truy vấn giao dịch. Nếu chạy trên cùng database primary, workload phân tích có thể cạnh tranh với INSERT/UPDATE/DELETE quan trọng.

Các chiến lược:

- Dùng read replica hoặc analytical store nếu phù hợp.
- Lên lịch full refresh và backfill vào giờ tải thấp.
- Giới hạn concurrency và tài nguyên cho pipeline.
- Chia nhỏ công việc theo partition hoặc tenant.
- Dùng connection pool riêng với giới hạn rõ.
- Đặt timeout và cancellation policy cho truy vấn phân tích.
- Theo dõi replication lag nếu đọc từ replica.
- Tránh transaction đọc kéo dài giữ snapshot và cản trở vacuum.

Replica giúp tách tải đọc nhưng có thể có độ trễ replication. Nếu freshness SLO là 5 giây mà replica lag thường 20 giây, việc chuyển sang replica không đáp ứng yêu cầu dù query latency giảm. Cần đánh giá cả freshness và query latency.

## 15. Chi phí tính toán và lưu trữ theo chu kỳ

Một pipeline refresh thường xuyên có thể có chi phí lớn hơn dự kiến vì chạy lặp lại trên toàn bộ dữ liệu. Cần ước lượng chi phí theo:

- Số lần refresh mỗi ngày.
- Thời gian CPU và elapsed mỗi lần.
- Số byte đọc và ghi.
- Kích thước bảng tổng hợp.
- Chi phí index maintenance.
- Chi phí lưu nhiều phiên bản snapshot.
- Chi phí backfill và retry.
- Chi phí replication và network transfer.

Mô hình khái quát:

~~~text
Chi phí ngày =
    số_lần_refresh × chi_phí_mỗi_lần
  + chi_phí_query_phục_vụ
  + chi_phí_lưu_trữ
  + chi_phí_backfill_và_retry
~~~

Mô hình này không thay thế hóa đơn hoặc số liệu tài nguyên thực tế. Nó giúp so sánh các thiết kế trên cùng workload. Một incremental refresh có thể cần thêm metadata và logic xử lý nhưng giảm lượng dữ liệu đọc lặp lại. Một materialized view lớn có thể giảm query CPU nhưng tăng storage và refresh cost.

## 16. Chọn kiến trúc theo yêu cầu nghiệp vụ

| Yêu cầu | Hướng kiến trúc nên đánh giá | Rủi ro cần đo |
|---|---|---|
| Dữ liệu mới nhất, truy vấn ít | Query trực tiếp | Latency và tải đột biến |
| Dữ liệu mới trong vài phút | Micro-batch hoặc incremental refresh | Backlog và retry |
| Dữ liệu mới trong vài giây | Streaming/CDC | Late events, vận hành và backpressure |
| Nhiều dashboard lặp lại cùng metric | Aggregate/materialized view/cache | Refresh lag và stale result |
| Báo cáo cuối ngày cần đối soát | Batch với snapshot và finalize | Thời gian hoàn tất và correction |
| Truy vấn lịch sử nặng, ít tương tác | Batch/warehouse hoặc workload riêng | Storage và thời gian xử lý |
| Cần vừa nhanh vừa chính xác cuối cùng | Kết quả provisional rồi finalize | Quản lý phiên bản và trạng thái |

Không nhất thiết chọn một kiến trúc cho toàn hệ thống. Có thể dùng streaming cho chỉ số vận hành, micro-batch cho dashboard quản trị và batch đối soát cuối ngày. Quan trọng là mỗi metric có định nghĩa freshness, accuracy và owner rõ ràng.
## 17. Ví dụ xuyên suốt: dashboard doanh thu theo tenant

Giả sử hệ thống có hàng trăm triệu đơn hàng. Dashboard cần hiển thị doanh thu theo tenant và giờ. Người dùng thường xem 24 giờ gần nhất, nhưng có thể mở báo cáo lịch sử nhiều tháng.

Nếu mọi request đều chạy aggregate trực tiếp trên orders, truy vấn có thể quét nhiều hàng và làm primary chịu tải. Nếu refresh toàn bộ materialized view mỗi phút, chi phí tính toán có thể rất cao.

Một thiết kế có thể gồm:

1. CDC hoặc pipeline incremental nhận thay đổi của orders.
2. Dữ liệu được gom theo event time và tenant.
3. Aggregate theo giờ được cập nhật theo cửa sổ gần đây.
4. Late event được phép điều chỉnh bucket trong thời hạn xác định.
5. Dashboard đọc bảng aggregate có index theo tenant_id và hour_bucket.
6. Báo cáo lịch sử dùng kho phân tích hoặc truy vấn batch riêng.
7. Job đối soát cuối ngày xác nhận số liệu đã finalized.

Schema tổng hợp minh họa:

~~~sql
CREATE TABLE hourly_revenue (
    tenant_id BIGINT NOT NULL,
    hour_bucket TIMESTAMP NOT NULL,
    order_count BIGINT NOT NULL,
    revenue NUMERIC(20, 2) NOT NULL,
    data_through TIMESTAMP NOT NULL,
    is_final BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (tenant_id, hour_bucket)
);
~~~

Truy vấn dashboard:

~~~sql
SELECT hour_bucket, order_count, revenue, data_through, is_final
FROM hourly_revenue
WHERE tenant_id = :tenant_id
  AND hour_bucket >= :from_hour
  AND hour_bucket < :to_hour
ORDER BY hour_bucket;
~~~

Index khóa chính có thể hỗ trợ truy vấn theo tenant và khoảng thời gian. Cần kiểm tra kế hoạch thực thi, số hàng đọc và kích thước kết quả. Nếu bảng tổng hợp được partition theo thời gian, thiết kế index và uniqueness phải tuân theo giới hạn của hệ quản trị.

Dashboard có thể hiển thị số liệu provisional trong cửa sổ gần nhất và trạng thái finalized cho bucket đã đối soát. Người dùng biết dữ liệu có thể điều chỉnh và biết kết quả đã được chốt đến đâu.

## 18. Thiết kế incremental update có thể chạy lại an toàn

Pipeline có thể bị retry do timeout hoặc lỗi worker. Nếu mỗi lần chạy lại chỉ cộng delta vào aggregate, cùng một sự kiện có thể được tính hai lần.

Một số cơ chế:

- Lưu event ID đã xử lý hoặc offset/checkpoint.
- Dùng batch ID và trạng thái xử lý.
- Dùng UPSERT thay thế aggregate của một bucket sau khi tính lại bucket đó.
- Áp dụng CDC theo log sequence/commit position có thể tiếp tục.
- Thiết kế phép cập nhật idempotent.
- Lưu version hoặc watermark của kết quả được publish.

Nếu có UPDATE/DELETE trên nguồn, cần biết sự kiện thay đổi tương ứng với delta âm/dương hoặc tính lại bucket. Không chỉ xử lý INSERT nếu nghiệp vụ cho phép sửa đơn hàng hoặc hủy giao dịch.

Khi publish kết quả, có thể ghi metadata gồm computed_at, data_through, source_version và is_final. Các trường này giúp người dùng và hệ thống giám sát xác định kết quả được tạo từ dữ liệu nào.

## 19. Backpressure và backlog

Khi tốc độ dữ liệu đầu vào lớn hơn tốc độ xử lý, backlog tăng. Dù pipeline đang chạy liên tục, freshness có thể ngày càng xấu.

Theo dõi:

- Số sự kiện hoặc byte đang chờ.
- Tuổi của sự kiện cũ nhất trong backlog.
- Input rate và processing rate.
- Thời gian xử lý từng batch/window.
- Số lần retry và lỗi poison message.
- Thời gian lag theo partition hoặc consumer.
- Tác động của backfill lên xử lý dữ liệu mới.

Nếu backlog tăng, có thể tăng worker hoặc parallelism, nhưng cần xem database và downstream có chịu được tải thêm không. Tăng consumer có thể làm tăng contention, connection count, lock và I/O. Đôi khi cần giảm phạm vi xử lý, ưu tiên dữ liệu mới, giới hạn backfill hoặc tách workload.

Không chỉ xem trạng thái worker là healthy. Một worker có thể chạy bình thường nhưng xử lý chậm hơn tốc độ đầu vào.
## 20. Đo latency, freshness và compute cùng lúc

Một dashboard quan sát nên thể hiện ba nhóm chỉ số trên cùng trục thời gian:

| Nhóm | Chỉ số nên theo dõi |
|---|---|
| Freshness | Event-time lag, ingestion lag, data_through, watermark, backlog age |
| Query latency | p50/p95/p99, timeout rate, queue time, connection wait |
| Compute | CPU seconds, memory peak, bytes read/written, temp I/O, refresh duration |
| Storage | Kích thước aggregate/cache, growth rate, index size |
| Correctness | Số event nhận/xử lý, duplicate, late correction, reconciliation delta |
| Concurrency | Active queries, worker count, pool wait, lock wait, replication lag |

Khi một lần refresh bắt đầu thường xuyên hơn, hãy kiểm tra compute cost có tăng theo số lần chạy hay không. Khi cache TTL tăng, hãy kiểm tra freshness lag và hit ratio. Khi query latency giảm sau precompute, hãy đo cả chi phí refresh và lưu trữ.

Không tối ưu một chỉ số riêng lẻ. Một cấu hình có p95 tốt nhưng freshness vượt SLO hoặc chi phí tăng gấp nhiều lần chưa chắc là cải thiện.

## 21. Quy trình tìm điểm cân bằng

Một quy trình có thể áp dụng:

1. **Phân loại quyết định nghiệp vụ:** người dùng cần hành động gì từ metric và cần dữ liệu mới đến đâu?
2. **Định nghĩa freshness:** chọn event time, ingestion time, data_through và giới hạn late arrival.
3. **Định nghĩa latency SLO:** đo p50/p95/p99 cho truy vấn đại diện.
4. **Đo baseline:** query cost, refresh duration, bytes scanned, CPU, I/O và storage.
5. **Xác định mẫu truy cập:** tần suất truy vấn, phạm vi thời gian, tenant và concurrency.
6. **Chọn cách tính:** query trực tiếp, batch, micro-batch, streaming hoặc kết hợp.
7. **Đánh giá precompute/cache:** xác định metric có được dùng lặp lại đủ nhiều để bù chi phí lưu và refresh không.
8. **Thiết kế correctness:** snapshot, watermark, late event, deduplication, idempotency và finalize.
9. **Cô lập workload:** giới hạn tài nguyên và bảo vệ OLTP.
10. **Thử nhiều chu kỳ:** đo freshness, latency, compute và backlog dưới tải đại diện.
11. **Thử tình huống lỗi:** nguồn trễ, worker restart, retry, duplicate và backfill.
12. **Chọn điểm cân bằng:** đáp ứng SLO với chi phí và rủi ro vận hành chấp nhận được.
13. **Theo dõi liên tục:** cảnh báo khi freshness, latency hoặc cost vượt ngưỡng.

## 22. Các sai lầm thường gặp

- **Đồng nhất thời điểm refresh với freshness.** Refresh xong không có nghĩa dữ liệu nguồn đã đầy đủ đến thời điểm đó.
- **Chỉ đo latency trung bình.** p95/p99 có thể xấu dù trung bình tốt.
- **Làm mới càng thường xuyên càng tốt.** Refresh dày có thể lặp lại nhiều công việc và tăng I/O.
- **Tính trước mọi metric.** Bảng tổng hợp và index có chi phí lưu trữ, cập nhật và consistency.
- **Cache quá lâu mà không công bố độ cũ.** Người dùng có thể ra quyết định trên số liệu đã lỗi thời.
- **Streaming được xem là chính xác tức thời.** Late events, watermark và nguồn chậm vẫn tạo độ trễ hoặc correction.
- **Incremental update không idempotent.** Retry có thể cộng trùng hoặc bỏ sót delta.
- **Bỏ qua UPDATE/DELETE của dữ liệu nguồn.** Aggregate chỉ xử lý INSERT có thể sai dần theo thời gian.
- **Backfill chạy cùng ưu tiên với dữ liệu mới.** Dữ liệu mới có thể bị backlog kéo dài.
- **Chạy phân tích nặng trên primary mà không giới hạn.** Có thể ảnh hưởng transaction và độ trễ OLTP.
- **Đánh giá replica chỉ theo query latency.** Replication lag có thể làm freshness không đạt yêu cầu.
- **Tối ưu chi phí compute nhưng bỏ qua chi phí vận hành.** Streaming hoặc cache phức tạp có thể tăng công sức giám sát và phục hồi.

## 23. Checklist lựa chọn độ tươi, latency và compute

- [ ] Đã xác định quyết định nghiệp vụ cần hỗ trợ.
- [ ] Đã định nghĩa freshness theo event time hoặc mốc rõ ràng.
- [ ] Đã tách freshness khỏi query response latency.
- [ ] Đã đặt SLO cho p50/p95/p99 và tỷ lệ dữ liệu đạt freshness.
- [ ] Đã đo baseline CPU, memory, I/O, bytes scanned và storage.
- [ ] Đã đánh giá query trực tiếp so với batch, micro-batch và streaming.
- [ ] Đã xác định metric nào nên precompute hoặc cache.
- [ ] Đã hiểu semantics refresh của hệ quản trị đang dùng.
- [ ] Đã xử lý late events, watermark, duplicate và correction.
- [ ] Đã thiết kế incremental update có idempotency/checkpoint.
- [ ] Đã xác định khi nào dữ liệu provisional và khi nào finalized.
- [ ] Đã giới hạn concurrency và bảo vệ workload giao dịch.
- [ ] Đã theo dõi backlog, input rate và processing rate.
- [ ] Đã benchmark dưới tải đại diện và tình huống lỗi.
- [ ] Đã so sánh tổng chi phí pipeline, query, storage và vận hành.
- [ ] Đã công bố data_through hoặc trạng thái freshness cho người dùng.

## 24. Nguyên tắc cần ghi nhớ

Độ tươi dữ liệu, thời gian phản hồi và chi phí tính toán là ba mục tiêu phải được thiết kế cùng nhau. Query trực tiếp có thể cho dữ liệu mới nhưng tốn tài nguyên; batch giảm overhead nhưng tăng độ trễ; micro-batch và streaming rút ngắn độ trễ với yêu cầu vận hành cao hơn; aggregate, materialized view và cache làm truy vấn nhanh nhưng cần quản lý refresh và dữ liệu cũ.

Hãy bắt đầu từ quyết định nghiệp vụ và SLO, đo freshness theo event time, đo latency bằng p50/p95/p99 và tính compute trên toàn pipeline. Thiết kế watermark, late-event correction, idempotency và trạng thái finalized để giữ đúng số liệu. Chọn cách tính phù hợp cho từng workload, cô lập tải phân tích khỏi giao dịch và kiểm chứng dưới concurrency thực tế. Điểm cân bằng tốt là đáp ứng yêu cầu nghiệp vụ với chi phí có thể dự đoán, dữ liệu có trạng thái rõ ràng và hiệu năng ổn định.
