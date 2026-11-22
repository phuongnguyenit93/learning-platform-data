# 2.5 Chọn khoảng lấy mẫu, thời lượng quan sát và cửa sổ xảy ra sự cố

## Mục tiêu học tập

Trong chẩn đoán Java/JVM, công cụ đo có thể hoạt động đúng nhưng kết luận vẫn sai vì **lấy mẫu quá thưa**, **quan sát quá ngắn**, hoặc **chọn cửa sổ thời gian không trùng lúc sự cố xảy ra**. Bài này giúp bạn thiết kế phép đo có đủ độ phân giải và tính đại diện, giới hạn được overhead, đồng thời giữ được bằng chứng trước, trong và sau sự cố.

Sau bài học, bạn có thể:

- Phân biệt khoảng lấy mẫu, chu kỳ thu thập/xuất metrics, cửa sổ gom nhóm dữ liệu, bước hiển thị biểu đồ, thời lượng phiên đo và cửa sổ sự cố.
- Ước lượng số điểm dữ liệu/mẫu thống kê cần có để trả lời một câu hỏi, hiểu tác động của việc mất mẫu và lấy mẫu lệch thời điểm.
- Chọn cấu hình phù hợp cho metrics, logs/traces, JFR, CPU/allocation profiler, thread dump và các sự cố xảy ra chớp nhoáng.
- Thiết kế các cửa sổ **trước – trong – sau** một incident để đối chiếu baseline, xác minh giả thuyết và kiểm tra hồi phục.
- Ghi lại đủ thời gian, đơn vị, cấu hình và giới hạn của phép đo để người khác có thể tái hiện và đánh giá kết luận.

## 1. Trước khi chọn con số: hiểu rõ đang đo cái gì

Hãy tách riêng các khái niệm sau; gọi tất cả là “sampling interval” sẽ dẫn đến nhầm lẫn:

| Khái niệm | Ký hiệu dùng trong bài | Ý nghĩa | Ví dụ |
| --- | --- | --- | --- |
| **Khoảng lấy mẫu** (*sample interval*) | `Δs` | Khoảng giữa hai lần lấy giá trị/stack sample theo thiết kế | CPU sampling mỗi 10 ms, đọc gauge mỗi 1 s |
| **Chu kỳ scrape/collection/export** | `Δc` | Khoảng hệ thống thu hoặc chuyển dữ liệu từ tiến trình sang hệ quan sát | Prometheus scrape mỗi 15 s; exporter gửi metrics mỗi 30 s |
| **Cửa sổ tổng hợp** (*aggregation window*) | `Wagg` | Khoảng sự kiện/mẫu được gộp thành rate, average, max, histogram, percentile | `rate(...[5m])`; p95 tính trên 5 phút |
| **Bước hiển thị/truy vấn** (*chart/query step*) | `Δq` | Khoảng cách giữa các điểm do dashboard vẽ hoặc truy vấn trả về | Biểu đồ hiển thị một điểm mỗi 60 s |
| **Thời lượng quan sát** | `Tobs` | Toàn bộ khoảng bắt đầu–kết thúc thu/giữ bằng chứng | Ghi JFR 2 phút; theo dõi heap 6 giờ |
| **Cửa sổ sự cố** (*incident window*) | `Winc` | Khoảng thời gian có sự cố và các đoạn baseline/phục hồi cần so sánh | Từ 10:22:14 đến 10:23:02 UTC, kèm trước/sau |

Một metric là **gauge** có thể chỉ giữ giá trị cuối tại lúc collection; một **counter** là tổng tích lũy (cần tính chênh lệch/rate trên thời gian); một **histogram** gộp nhiều observation giữa các lần xuất dữ liệu mà vẫn giữ được phân phối theo bucket. Với **event recording** (log, trace, JFR event), dữ liệu gốc có timestamp riêng, nên không tương đương việc chỉ đọc một giá trị tức thời theo chu kỳ.

### Chuỗi đo thực tế

```text
Sự kiện / trạng thái ứng dụng
          |
          v
Instrumentation, polling hoặc sampling [Δs / event-driven]
          |
          v
Gom theo khoảng, rate, histogram, drop/filter [Wagg]
          |
          v
Buffer -> collector -> storage / retention [Δc, độ trễ]
          |
          v
Truy vấn, downsampling, dashboard [Δq]
          |
          v
Kết luận về thời điểm và nguyên nhân
```

Nếu sự cố kéo dài 8 giây, ứng dụng vẫn có thể phát ra hàng nghìn request. Một histogram latency được cập nhật **mỗi request** có thể giữ số lượng request chậm, dù hệ thống xuất histogram mỗi 30 giây. Ngược lại, gauge `last_request_duration` chỉ được đọc tại mỗi phút có thể bỏ lỡ toàn bộ 8 giây đó. Tương tự, dashboard dùng `Δq = 5m` có thể làm mờ một đột biến mà dữ liệu gốc với bước 15 s vẫn còn.

**Điểm quan trọng:** tăng tần suất scrape không khắc phục dữ liệu đã bị gộp mất chi tiết trước đó; thu thập ở độ phân giải cao nhưng truy vấn ở độ phân giải thấp cũng có thể che tín hiệu. Kiểm tra **từ nơi đo đến nơi hiển thị**, không chỉ thông số trên dashboard.

## 2. Chọn khoảng lấy mẫu theo thời gian tồn tại của tín hiệu

Bước đầu tiên là nêu **câu hỏi chẩn đoán** và **độ dài đặc trưng của hiện tượng**.

| Tình huống | Tín hiệu cần thấy | Hướng chọn phương pháp/độ phân giải | Điều cần tránh |
| --- | --- | --- | --- |
| CPU JVM tăng liên tục 10–20 phút | CPU process, runnable threads, throughput | Metrics mức vài giây đến vài chục giây thường đủ để thấy xu hướng; profiling trong lúc CPU cao để tìm hotspot | Dựa vào trung bình 1 giờ để kết luận không có peak |
| GC pause khoảng vài chục–vài trăm ms | GC pause duration và timestamp | **JFR/GC events hoặc histogram pause**, vì sự kiện được ghi khi xảy ra | Chỉ nhìn heap gauge được scrape mỗi 30 s rồi suy luận không có pause |
| Request chậm từng đợt 5–10 s | Request latency, count, traces, queue, pool | Histogram/counter cập nhật mỗi request, trace/error span và dashboard bước ngắn phù hợp | Chỉ scrape gauge `last` mỗi 1 phút |
| Lock contention tái diễn trong 1–2 phút | Thread state, JFR lock/park events, blocked time | Recording bao trùm thời điểm treo; lấy nhiều thread snapshot có giãn cách và giới hạn overhead | Xem một thread dump rồi gán ngay nguyên nhân |
| CPU hotspot chỉ khi batch job chạy 45 s | CPU samples trong pha batch | Bắt đầu recording trước khi job chạy; dùng profiler có tần suất và thời lượng đủ cho pha 45 s | Profiling 5 phút sau khi batch kết thúc |
| Memory tăng dần theo giờ | Live heap, RSS, allocation, GC, workload | Theo dõi nhiều chu kỳ tải/GC trong hàng giờ; so sánh cùng trạng thái hệ thống | Kết luận leak chỉ từ hai ảnh heap cách nhau vài giây |

Đối với tín hiệu có độ dài ngắn nhất cần phát hiện là `τ`, một cách **ước lượng ban đầu** cho phép đo giá trị tức thời là chọn `Δs` nhỏ hơn `τ` nhiều lần (chẳng hạn `Δs ≤ τ/4`) để cố gắng thấy vài điểm trong một lần xảy ra hiện tượng. Đây **không phải ngưỡng đảm bảo**: đồng hồ lệch pha, jitter, collector quá tải, missing samples và việc làm trơn dữ liệu có thể vẫn che sự cố. Việc theo mẫu định kỳ cũng có thể mắc **aliasing**: các dao động lặp lại trùng nhịp thu mẫu khiến dữ liệu trông ổn định giả tạo.

Không nên diễn giải định lý Nyquist như lời bảo đảm “scrape gấp đôi tần số lỗi thì bắt được lỗi”; Nyquist áp dụng cho tín hiệu liên tục được giới hạn băng tần trong điều kiện lấy mẫu phù hợp, không tự áp dụng cho spike ngắn, counters, trace được chọn mẫu hay các sự kiện không tuần hoàn. Nếu một hiện tượng hiếm chỉ tồn tại vài mili-giây, **event-based instrumentation** hoặc histogram thường phù hợp hơn việc cố scrape toàn bộ gauge mỗi mili-giây.

### Quy tắc lựa chọn theo loại dữ liệu

**Gauge:** lấy mẫu đủ nhanh so với tốc độ thay đổi cần quan sát, và đừng coi khoảng trống giữa hai điểm là bằng chứng không có spike. Gauge đã giữ “giá trị cuối cùng” không tái tạo được giá trị lớn nhất từng xảy ra trong khoảng đó.

**Counter:** thu thập counter tích lũy rồi tính thay đổi theo thời gian thực tế; kiểm tra counter reset khi restart, mất mẫu và chu kỳ collection. Ví dụ: counter tăng từ 1.000 lên 1.180 trong 30 s thì tốc độ trung bình trên **khoảng đó** là `180/30 = 6 events/s`; không được gán rằng mọi giây trong khoảng đều có chính xác 6 event.

**Histogram/summary:** xác định số sự kiện thực sự ghi vào phân phối và phạm vi aggregation. Với latency, p99 cần đủ request trong cửa sổ; vài request thì giá trị p99 khó dùng để kết luận độ ổn định dài hạn. Các p95/p99 của từng phút **không thể lấy trung bình số học** để có p95/p99 của 10 phút; phải gộp phân phối có thể tổng hợp hoặc đo lại trên dữ liệu thô.

**Logs/traces:** phần lớn là sự kiện có timestamp; ngoài `Δc`, cần biết log sampling, head/tail trace sampling, dropped spans, buffering, clock skew và độ trễ xuất dữ liệu. Nếu lỗi rất hiếm mà chỉ lấy 1% trace ngẫu nhiên, có thể không thấy trace lỗi dù incident đã xảy ra. Chính sách giữ error trace hoặc tail sampling cần cân nhắc overhead và thời gian quyết định.

**Profiler/JFR:** cần phân biệt *tần suất stack sampling* với *thời lượng recording* và *ngưỡng/tần suất từng loại event*. Nhiều sự kiện JFR được ghi khi có event và theo cấu hình; không có một `Δs` duy nhất cho mọi loại JFR event. Thread dump là ảnh trạng thái tại thời điểm gọi, không mặc nhiên là chuỗi mẫu profiling thống kê.

## 3. Chọn thời lượng quan sát để dữ liệu có tính đại diện

Một cách tính gần đúng cho polling đều đặn là:

```text
N kỳ vọng ≈ Tobs / Δs     (không tính chi tiết điểm đầu/cuối)
Tobs ≈ N mục tiêu × Δs
```

Đây là **số mẫu dự kiến**, không phải mẫu hợp lệ thực nhận. Cần đếm thực tế khi có timeout, pause, miss, backpressure, restart hoặc khi công cụ chỉ lấy mẫu các thread đang ở trạng thái phù hợp.

Ví dụ `Δs = 15 s`, `Tobs = 5 phút` cho khoảng `20` khoảng lấy mẫu; số điểm còn tùy lịch lấy mẫu. Dữ liệu này đủ để nhìn xu hướng ngắn hạn của một gauge ổn định, **không đủ để khẳng định** đã bắt được spike 1 giây. Một đường biểu đồ có 20 điểm cũng không tự nói lên 20 request: đó có thể là 20 giá trị đã gộp từ hàng nghìn request.

Đối với profiler, nếu công cụ **thực sự thu 100 stack samples/giây** trong 60 giây, số mẫu danh nghĩa khoảng `6.000`. Mẫu thực thu có thể ít hơn do thread không chạy, độ trễ sampling, lọc event và tải hệ thống. Khi một method chỉ chiếm tỷ trọng rất nhỏ của số mẫu, hãy tăng thời lượng/đúng thời điểm workload hoặc dùng công cụ phù hợp; tăng sample rate vô hạn không thay cho dữ liệu đại diện và có thể làm tăng overhead.

### Ba điều quyết định độ dài

1. **Bao trùm vòng đời hiện tượng:** job 45 giây cần capture bắt đầu trước khi job chạy, xuyên suốt job và một đoạn sau; memory leak cần quan sát nhiều pha GC/workload, có thể kéo dài hàng giờ. Chọn `Tobs` theo chu kỳ ứng dụng chứ không theo một con số chung.
2. **Đủ dữ liệu để so sánh:** lấy baseline trước sự cố, cửa sổ trong sự cố và sau can thiệp; các cửa sổ nên có lưu lượng, route, phiên bản và điều kiện tải tương đồng khi mục tiêu là so sánh hiệu năng.
3. **Giới hạn chi phí:** recording, profile, log và trace tốn CPU/I/O/memory/disk/network và có thể chứa dữ liệu nhạy cảm. Dùng sampling/retention phù hợp, định trước điều kiện dừng, không bật profile nặng không giới hạn chỉ để hy vọng trúng một lỗi hiếm.

Ví dụ, nếu lỗi trung bình 1 lần mỗi 40 phút nhưng chỉ kéo dài 4 giây, chạy profiler nặng 2 phút có xác suất bỏ lỡ lớn. Phương án khả thi hơn thường là telemetry nền nhẹ, **vòng đệm dữ liệu có giữ lại lịch sử** và trigger thu thêm khi error rate, latency hoặc log pattern vượt điều kiện. Đừng nói “không tái hiện được” chỉ vì thời lượng đo không bao trùm cơ hội xảy ra lỗi.

## 4. Cửa sổ xảy ra sự cố: lấy đủ phần trước, trong và sau

Định nghĩa rõ các mốc thời gian theo **một múi giờ thống nhất** (nên lưu UTC trong dữ liệu):

- `t_detect`: hệ thống/nhân sự **phát hiện** sự cố; thường trễ hơn lúc bắt đầu.
- `t_start`: dấu hiệu sớm nhất có bằng chứng của sự cố, có thể là ước lượng với độ bất định.
- `t_end`: thời điểm triệu chứng kết thúc theo tiêu chí xác định; khác thời điểm tắt cảnh báo nếu alert có delay/hysteresis.
- `t_change`: thời điểm triển khai bản mới, thay config hoặc chạy thử; đánh dấu riêng để không nhầm với mốc sự cố.

Đề xuất chia khoảng:

```text
t_pre              t_start             t_end               t_post
|------------------|===================|-------------------|
       BASELINE          INCIDENT             RECOVERY
     trước sự cố       trong sự cố          sau / sau thay đổi
```

Ví dụ: spike latency được ghi nhận ở `10:22:14Z–10:23:02Z` (48 giây). Có thể chọn baseline `10:17:00Z–10:22:14Z`, incident `10:22:14Z–10:23:02Z`, recovery `10:23:02Z–10:28:00Z`. Đây là **ví dụ phương pháp**, không phải một quy tắc 5 phút áp cho mọi hệ thống.

Các khoảng cần đủ dài để nhìn background trend, GC/workload lân cận và kiểm chứng hồi phục, nhưng cũng đủ hẹp để không pha loãng một sự cố 48 giây vào một trung bình 1 giờ. Với truy vấn có tính cửa sổ, hãy xác định chính xác timestamp nào được tính vào khoảng; quy ước thường dùng là `[start, end)`. Nếu một điểm `rate(...[5m])` ở 10:25 chứa dữ liệu từ 10:20 đến 10:25, nó **không phải** số đo chỉ tại 10:25.

### Điều gì có thể làm lệch cửa sổ?

- **Clock skew** giữa các node: logs, traces, DB và metrics có thể có timestamp lệch vài giây; so sánh cần đồng bộ NTP và ghi mức sai lệch khi có.
- **Độ trễ ingest/export:** sự kiện xảy ra lúc 10:22 nhưng xuất hiện trên dashboard lúc 10:24; đặt cửa sổ theo *event time* nếu dữ liệu hỗ trợ, không đồng nhất thời điểm hiển thị với thời điểm xảy ra.
- **Thời điểm scrape lệch pha:** một process được scrape tại giây 02, node khác tại giây 11; “cùng một điểm phút” thực chất bao gồm những thời điểm khác nhau.
- **Rolling/window smoothing:** biểu đồ “average 5m” có thể tiếp tục cao sau khi sự cố đã kết thúc hoặc bắt đầu tăng muộn so với spike.
- **Restart/GC/deployment:** reset counter, thay instance hoặc warm-up JIT có thể làm mẫu trước và sau không cùng quần thể.
- **Thiếu dữ liệu:** khoảng trống phải đánh dấu là *missing/no data*, không tự biến thành zero hay coi là hành vi bình thường.

Khi chưa xác định chắc `t_start`, ghi cả khoảng bất định, ví dụ “xảy ra trong khoảng 10:21:45Z–10:22:14Z”; hãy mở rộng vùng trích bằng chứng tương ứng. Đặc biệt, dữ liệu **trước lúc phát hiện** thường quan trọng hơn việc bật profile sau khi incident đã qua.

## 5. Trước, trong và sau: thiết kế phương pháp đo theo câu hỏi

### A. Khi cần theo dõi sức khỏe thông thường

Giữ metrics có chi phí thấp đủ lâu để nhìn xu hướng: request rate, error rate, duration distribution, CPU, heap/RSS, GC, thread pool, queue và saturation. Chu kỳ 10–30 giây có thể là điểm thử ban đầu cho một số hệ thống, nhưng cần điều chỉnh theo SLA, tần suất spike, độ đắt của exporter, cardinality và dung lượng lưu trữ. Với hành vi sub-second, đo bằng event/histogram hoặc tracing thích hợp.

Đặt `Δq` dashboard phù hợp với `Δc`, tránh vẽ đường “mượt” bằng nội suy khiến người đọc nhầm đó là điểm đo thật. Mỗi biểu đồ nên biết **đơn vị**, **thời gian gộp**, **khoảng lấy mẫu** và **hàm tổng hợp**.

### B. Khi cần profile một pha tải cụ thể

Bắt đầu recording **trước khi pha tải đến**, bao trùm warm-up/steady-state hoặc giữ từng pha tách bạch, ghi timestamp của giai đoạn cần phân tích và chốt thời gian dừng. Nếu mục tiêu là bottleneck ở steady-state, không gộp startup JIT/class loading vào kết luận. Nếu mục tiêu là startup chậm thì chính warm-up mới phải được đo.

Đối chiếu profile với CPU process, throughput và latency cùng khoảng. Một CPU profile có ít mẫu ở một method không chứng minh method ấy không chậm do blocking, I/O hoặc lock; có thể cần wall-clock/lock events.

### C. Khi cần truy vết incident hiếm đã phát hiện muộn

Duy trì cơ chế thu nhẹ theo thời gian có khả năng **giữ lại vài phút trước trigger** (metrics đủ retention, logging có cấu trúc, JFR vòng đệm với `maxage`/`maxsize` phù hợp). Khi cảnh báo xuất hiện: đánh dấu `t_detect`, trích dữ liệu trước trigger, thu thêm ở độ phân giải cao nếu an toàn, rồi dừng phần thu bổ sung.

Không thể quay ngược thời gian để khôi phục stack samples hoặc raw requests đã bị bỏ nếu trước đó không ghi. Bật profiler sau khi service hết chậm chỉ có thể quan sát trạng thái *sau sự cố*; phải ghi rõ giới hạn bằng chứng.

### D. Khi đo hiệu quả của một thay đổi

So sánh cửa sổ `W_before` và `W_after` có tải, route, version, cache, data set và điều kiện mạng càng tương đương càng tốt. Ghi rõ thời điểm change và dành khoảng ổn định sau change trước khi tính kết quả (tùy cache warm-up, rollout, JIT). Nếu lượng request trước là 10.000 và sau là 12, phân vị latency sau rất kém ổn định; không nên chỉ so hai p99 rồi tuyên bố cải thiện.

Nếu workload có chu kỳ ngày/tuần, baseline “5 phút ngay trước sự cố” có thể không đại diện: thêm khung giờ tương ứng của ngày trước hoặc baseline theo cùng loại traffic để tránh so sai bối cảnh.

## 6. Phân biệt metric window với số sự kiện thực sự được đo

Giả sử service ghi **mỗi request** vào classic histogram `http_request_duration_seconds`. Scrape 15 giây không có nghĩa service chỉ quan sát một request mỗi 15 giây; histogram bucket/count/sum đã tích lũy số lần ghi trong khoảng.

Ví dụ truy vấn PromQL sau dùng **tên metric giả định** để diễn giải khái niệm (môi trường thực tế có thể dùng tên và nhãn khác):

```promql
sum by (route) (rate(http_request_duration_seconds_count[5m]))
```

Đây là tốc độ request xấp xỉ trên mỗi `route` dựa trên cửa sổ 5 phút, không phải số request ở chính thời điểm điểm biểu đồ được vẽ. Muốn biết kích thước mẫu trong một khoảng, có thể xem lượng tăng counter tương ứng:

```promql
sum by (route) (increase(http_request_duration_seconds_count[5m]))
```

Ước lượng p95 từ **classic histogram buckets**:

```promql
histogram_quantile(
  0.95,
  sum by (le, route) (
    rate(http_request_duration_seconds_bucket[5m])
  )
)
```

- `[5m]` là **cửa sổ rate**, không phải chu kỳ scrape. Hai điểm biểu đồ cách nhau 30 giây có thể dùng **hai cửa sổ 5 phút chồng lấn mạnh**; đừng coi chúng độc lập.
- `histogram_quantile` là ước lượng từ bucket và chịu sai số độ rộng bucket; không tự chuyển từ “ước lượng” thành giá trị request chính xác. Cấu hình native histogram có hình thức truy vấn khác với ví dụ classic buckets này.
- Với sample count thấp, tỷ lệ request lỗi hoặc percentile có thể dao động mạnh. Cần ghi **số observation**, không chỉ percentile.
- Không lấy trung bình các `p95` từng instance để tạo `p95` toàn cluster; gộp các bucket counts hợp lệ trước khi tính quantile, nếu nhãn/bucket schema tương thích.
- Nếu counter reset do restart hoặc thiếu dữ liệu kéo dài, kiểm tra semantics của hàm rate/increase, tỷ lệ mẫu thực và metadata phiên đo; không dùng phép trừ thô để suy diễn throughput âm.

Nếu chỉ lưu **average latency** của từng cửa sổ 1 phút, không thể khôi phục p99 đã mất. Để bắt lỗi latency đuôi cao, cần đo phân phối ở nơi event xảy ra (histogram, trace phù hợp) và chọn cửa sổ có đủ request.

## 7. Ví dụ Java 17+: một spike biến mất trong snapshot thưa

Bài tập sau tạo **dữ liệu giả lập hoàn toàn xác định** gồm một phép đo latency tại mỗi giây trong 60 giây. Tất cả có giá trị `100 ms` ngoại trừ giây thứ `27` có giá trị `1900 ms`. Chúng ta so sánh:

- `snapshot`: chỉ xem giá trị ở đầu mỗi chu kỳ 10 giây, như một gauge được đọc thưa.
- `avg`: trung bình đủ 10 sự kiện đã xảy ra trong chu kỳ.
- `max`: giá trị lớn nhất trong đúng chu kỳ.

Tạo tệp **`SamplingWindowDemo.java`**:

```java
import java.util.Locale;

public class SamplingWindowDemo {
    private static long latencyAt(int second) {
        return second == 27 ? 1900L : 100L;
    }

    public static void main(String[] args) {
        for (int start = 0; start < 60; start += 10) {
            long sum = 0;
            long max = Long.MIN_VALUE;

            for (int second = start; second < start + 10; second++) {
                long latency = latencyAt(second);
                sum += latency;
                max = Math.max(max, latency);
            }

            System.out.printf(Locale.ROOT,
                    "[%02d,%02d): snapshot=%d ms | avg=%.0f ms | max=%d ms%n",
                    start, start + 10, latencyAt(start), sum / 10.0, max);
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac SamplingWindowDemo.java
java SamplingWindowDemo
```

**Stdout chính xác:**

```text
[00,10): snapshot=100 ms | avg=100 ms | max=100 ms
[10,20): snapshot=100 ms | avg=100 ms | max=100 ms
[20,30): snapshot=100 ms | avg=280 ms | max=1900 ms
[30,40): snapshot=100 ms | avg=100 ms | max=100 ms
[40,50): snapshot=100 ms | avg=100 ms | max=100 ms
[50,60): snapshot=100 ms | avg=100 ms | max=100 ms
```

Giải thích: trong cửa sổ `[20,30)` có 9 sự kiện `100 ms` và 1 sự kiện `1900 ms`; trung bình là `(9×100 + 1900)/10 = 280 ms`. Snapshot tại `t=20 s` chỉ thấy `100 ms`, nên bỏ sót spike. Average cho thấy thay đổi nhưng **không phản ánh độ nghiêm trọng của request chậm nhất**; max giữ được cực đại. Trong production, muốn biết tỷ lệ và phân phối request chậm, nên thu histogram/counters và đủ count; một giá trị max cũng có thể bị một outlier chi phối.

Điều demo **không mô phỏng**: jitter, đồng hồ chạy thật, đồng thời, missing samples, độ trễ xuất dữ liệu, percentile ước lượng từ buckets và chi phí đo. Đây là mô hình tối giản để phân biệt **mẫu tức thời** với **thống kê của toàn bộ sự kiện trong cửa sổ**.

### Đồng hồ và thời lượng trong code thực tế

Nếu tự xây công cụ đo, dùng `System.nanoTime()` để tính **thời lượng trong cùng tiến trình**, và dùng `Instant.now()`/timestamp chuẩn để tương quan sự kiện giữa hệ thống. Đo duration bằng chênh `Instant.now()` có thể bị ảnh hưởng bởi đồng hồ hệ thống thay đổi; ngược lại, giá trị `System.nanoTime()` không có ý nghĩa làm timestamp tuyệt đối giữa máy/process.

```java
// Đoạn minh họa đặt quanh một thao tác cần đo; không phải chương trình độc lập.
long startedNanos = System.nanoTime();
java.time.Instant eventTimeUtc = java.time.Instant.now();

performOperation();  // Phương thức của ứng dụng thực tế

long elapsedNanos = System.nanoTime() - startedNanos;
double elapsedMillis = elapsedNanos / 1_000_000.0;
```

Với scheduler/poller, ghi cả **thời điểm dự kiến** và **thời điểm thực tế** của mẫu. Nếu chu kỳ danh nghĩa là 1 s nhưng một lần GC pause làm khoảng thực thành 4 s, tính rate theo **4 s thực tế** và đánh dấu gap; không ép mẫu thành “đều 1 s” khi không có bằng chứng. Khi đọc `nanoTime`, đảm bảo phép đo nằm trong cùng JVM và dùng hiệu thời gian; không so hai số tuyệt đối từ hai JVM khác nhau.

## 8. JFR và công cụ JVM: gắn recording vào cửa sổ

Với JDK 21, `jcmd` có thể bắt đầu/dump/dừng Java Flight Recorder trên JVM mục tiêu; lệnh cần đúng PID và quyền attach. Trong các ví dụ, **12345 chỉ là PID giả định**, không được chạy nhầm trên tiến trình khác.

### Recording ngắn khi biết thời điểm sự cố

```bash
jcmd 12345 help JFR.start
jcmd 12345 JFR.start name=cpu-spike settings=profile duration=120s filename=cpu-spike.jfr
jcmd 12345 JFR.check
```

Hãy bắt đầu **trước hoặc ngay khi** spike có thể xảy ra và ghi lại mốc thời gian. File kết quả được ghi khi recording dừng; nếu `filename` là đường dẫn tương đối, kiểm tra thư mục làm việc/quyền ghi trên máy JVM. Chế độ `profile` thu nhiều dữ liệu hơn `default` và thường nên chạy **ngắn, có kiểm soát**. Không kỳ vọng recording 120 giây chứa sự cố đã kết thúc 10 phút trước khi bắt đầu.

### Vòng đệm liên tục để giữ vài phút trước alert

Trong trường hợp incident hiếm, có thể cân nhắc một recording `default` có giới hạn độ tuổi và kích thước dữ liệu:

```bash
jcmd 12345 JFR.start name=rolling settings=default disk=true maxage=15m maxsize=256m
jcmd 12345 JFR.check
```

Khi sự cố vừa xảy ra, dump phần lịch sử còn giữ:

```bash
jcmd 12345 JFR.dump name=rolling filename=incident.jfr maxage=10m
```

Sau khi không còn nhu cầu recording:

```bash
jcmd 12345 JFR.stop name=rolling
```

Đây là **ví dụ cách sử dụng tham số JDK 21**, không phải cấu hình mặc định được khuyến nghị cho mọi service. `maxage=15m` giới hạn **thời gian dữ liệu được giữ**, `maxsize=256m` giới hạn **dung lượng dữ liệu lưu**; khi tốc độ ghi cao, kích thước có thể khiến dữ liệu cũ bị loại trước 15 phút. Giá trị `maxsize` phải phù hợp giới hạn chunk thực tế của JVM. Recording `rolling` không tự dừng nếu không đặt `duration`, và `JFR.dump` **không dừng** recording.

JFR recording chỉ có những events được bật và thỏa ngưỡng/filter của cấu hình, không ghi toàn bộ mọi thứ JVM từng thực hiện. Khi phân tích, đọc event timestamps, các đoạn trống, sample counts, ứng dụng đang ở pha nào và trạng thái GC/threads; không coi sự vắng mặt của event là bằng chứng tuyệt đối rằng hiện tượng không tồn tại.

### Thread dump khác sampling profiler

```bash
jcmd 12345 Thread.print
```

Lệnh trên là **một snapshot**. Nếu cần xem trạng thái thay đổi, thu một số snapshot tại các mốc đã xác định, ghi timestamp và giới hạn tác động/tần suất. Việc gọi dump quá dày có thể gây overhead và tạo nhiều file lớn; các trạng thái `RUNNABLE`, `WAITING` hay `BLOCKED` ở một thời điểm không cho biết tỷ lệ CPU dài hạn.

Với sampling profiler chuyên dụng, xác định rõ sampling mode (CPU/on-CPU, wall-clock, allocation, lock), period, overhead, exclusions và điều kiện thread được tính. Số mẫu trên flame graph biểu thị phân phối theo **mode và thời lượng thực thu**, không tự chuyển thành số request hay số lần gọi method.

## 9. Trade-off giữa độ phân giải, độ dài và chi phí

Thời lượng dài ở độ phân giải cao cho nhiều bằng chứng hơn nhưng không miễn phí. Với dữ liệu polling, số điểm thô xấp xỉ:

```text
points ≈ number_of_series × (Tobs / Δc)
```

Ví dụ có **600 time series** trong 1 giờ:

| Chu kỳ thu | Điểm lý thuyết/series | Tổng điểm thô |
| --- | ---: | ---: |
| 60 s | 60 | 36.000 |
| 15 s | 240 | 144.000 |
| 5 s | 720 | 432.000 |

Đây là **ước lượng số điểm**, không phải byte lưu trữ hay chi phí CPU trực tiếp; hệ thống còn compression, metadata, retention và query overhead. Nếu nhãn metric chứa `userId`, `requestId`, URL chưa chuẩn hóa hoặc giá trị có cardinality lớn, số series có thể tăng mạnh ngoài dự tính. Tăng tần suất scrape khi không có khả năng lưu/query thích hợp gây mất mẫu và tăng nhiễu.

Với traces/logs/JFR, chi phí còn phụ thuộc **số events/giây, kích thước event, stack depth, sampling policy, chu kỳ flush, retention và tốc độ ghi disk**. Recording quá chi tiết có thể làm chính service chậm đi; phải lấy baseline overhead và kiểm tra tác động, nhất là trên production.

Một chiến lược thực tế là **đa độ phân giải**:

1. Theo dõi nền liên tục bằng tín hiệu ít tốn chi phí và có retention dài để biết *khi nào/ở đâu*.
2. Dùng histogram và event timestamp để không mất những tín hiệu ngắn quan trọng.
3. Dùng rolling buffer hoặc trigger để giữ bằng chứng **trước và trong incident**.
4. Bật profiler/JFR chi tiết trong khoảng đo giới hạn khi cần phân tích sâu; ngừng sau khi đã có dữ liệu.
5. Downsample dữ liệu cũ cho xu hướng dài hạn, nhưng giữ evidence thô quan trọng cho sự cố và ghi giới hạn retention.

Chọn mẫu có độ phân giải vừa đủ với mục tiêu, sau đó **kiểm chứng số mẫu thực thu**. “Đặt 10 ms” không đồng nghĩa “mỗi 10 ms có một mẫu hợp lệ”.

## 10. Quy trình lựa chọn từng bước

Hãy điền bằng chứng cho từng quyết định trước khi thu thập:

| Bước | Câu hỏi cần trả lời | Ví dụ câu trả lời đủ cụ thể |
| --- | --- | --- |
| 1. Mục tiêu | Muốn xác định điều gì? | “Có GC pause trùng p99 spike 30 s không?” |
| 2. Thời gian hiện tượng | Ngắn nhất dài bao lâu? Xảy ra định kỳ hay hiếm? | “Spike 5–30 s, khoảng 2 lần/giờ” |
| 3. Loại tín hiệu | Gauge, counter, histogram, event hay sample stack? | “Histogram request latency + JFR GC events” |
| 4. Chu kỳ | `Δs`, `Δc`, `Wagg`, `Δq` là bao nhiêu? | “Scrape 15 s; rate cửa sổ 1m và 5m; raw events giữ timestamp” |
| 5. Tổng thời lượng | Cần bao nhiêu vòng tải/sự kiện và mẫu hợp lệ? | “Theo dõi nền 2h; recording chi tiết 120s khi trigger” |
| 6. Incident window | Baseline/in-incident/recovery bắt đầu/kết thúc lúc nào? | “5 phút trước, toàn bộ spike, 5 phút sau, UTC” |
| 7. Overhead và retention | CPU, I/O, disk, băng thông, dữ liệu nhạy cảm, thời hạn? | “JFR profile ngắn; rolling default có giới hạn dung lượng” |
| 8. Kiểm chứng | Dữ liệu có đúng loại, đúng giờ, đủ mẫu, cùng phiên bản/tải? | “Kiểm tra timestamp, gaps, count, scrape lag và restart” |

Không có một cặp `Δs`/`Tobs` tối ưu cho mọi sự cố. Quyết định hợp lý phải bắt đầu từ **hiện tượng cần nhận diện**, **bằng chứng cần cho kết luận** và **chi phí/tác động chấp nhận được**.

### Mẫu ghi chép một phiên đo

```text
Mục tiêu: xác định bottleneck của request chậm trong batch chạy lúc 14:00 UTC
Dịch vụ/JDK/build: tên service, JDK version, commit/release cụ thể
Phạm vi: node/pod/route/tenant có ảnh hưởng
Time zone: UTC; đồng bộ đồng hồ và độ lệch quan sát được
Sự cố: t_start, t_detect, t_end (cùng mức bất định)
Baseline: [t_pre, t_start)
Incident: [t_start, t_end)
Recovery: [t_end, t_post)
Tín hiệu: CPU process + request histogram + JFR sample/lock events
Collection/sampling: Δs, Δc, Wagg, Δq, timestamp event
Recording: start/end thực tế; setting; sampling mode; dung lượng file
Data quality: số điểm kỳ vọng/thực thu; gaps; resets; dropped events
Bối cảnh: request rate, data set, deployment/config change, GC/workload phase
Kết luận: dữ liệu xác nhận điều gì, điều gì vẫn chỉ là giả thuyết
```

Dòng “số điểm kỳ vọng/thực thu” là bước QA cốt lõi: nếu định thu 120 điểm nhưng chỉ nhận 40 vì collector bị quá tải, phải đánh giá lại độ tin cậy trước khi diễn giải biểu đồ.

## 11. Sai lầm phổ biến và cách sửa

| Sai lầm | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| “Scrape mỗi 1 phút nên mọi spike dưới 1 phút đều mất.” | Với gauge có thể mất; histogram/event được ghi liên tục có thể vẫn giữ số liệu spike. | Kiểm tra loại dữ liệu và nơi aggregation diễn ra. |
| “Dashboard đang vẽ 1 điểm/5 phút, dữ liệu gốc cũng chỉ có vậy.” | Query step/downsampling có thể bỏ chi tiết so với storage. | Kiểm tra raw resolution, query range, hàm tổng hợp và retention. |
| “20 điểm metrics tức là 20 request.” | Điểm có thể là giá trị tổng hợp từ hàng nghìn sự kiện. | Xem `count` và cách ghi measurement. |
| “Lấy 100 Hz trong 60 giây chắc chắn có 6.000 mẫu hữu ích.” | Mẫu thực phụ thuộc sampler, thread state, filters, pauses và overhead. | Xem số mẫu thực, sampling mode và giai đoạn tải. |
| “Quan sát 5 phút không thấy lỗi nên lỗi không tồn tại.” | Incident hiếm, sai thời điểm, không có pre-buffer hoặc dùng sai tín hiệu. | Ghi tần suất lỗi, dùng event trigger/rolling retention và tăng coverage. |
| “Phân vị p99 sau thay đổi thấp hơn nên đã cải thiện.” | Mẫu nhỏ hoặc workload trước/sau khác nhau; percentiles có sai số ước lượng. | So sánh cùng nhóm traffic, số mẫu, thời lượng, histogram và độ bất định. |
| “Bỏ những khoảng no-data thành 0 để biểu đồ đẹp hơn.” | Tạo tín hiệu giả, có thể bị hiểu là service hồi phục hoặc không có request. | Giữ trạng thái missing và điều tra collector/network/restart. |
| “Profile sau sự cố là profile của sự cố.” | Mô tả workload tại thời điểm thu, có thể khác hoàn toàn lúc lỗi. | Thu trước/during trigger hoặc đánh dấu rõ giới hạn. |
| “Một mức 15 s/5m là quy tắc bất biến.” | Thang thời gian của GC pause, CPU trend, memory leak khác nhau. | Lựa chọn riêng theo tín hiệu, câu hỏi, overhead và retention. |

## 12. Tình huống tự kiểm tra

**1. Request latency p99 thỉnh thoảng tăng trong 3 giây, scrape mỗi 30 giây. Có cần đặt scrape 100 ms?**

Chưa chắc. Hãy xem metric latency có phải histogram được cập nhật **mỗi request** hay gauge tức thời. Nếu histogram đầy đủ, scrape 30 giây có thể vẫn mang thông tin về requests chậm. Để định vị chính xác **3 giây nào**, cần sự kiện/traces có timestamp hoặc metric có cửa sổ đủ hẹp; giảm scrape xuống 100 ms có thể gây overhead vô ích mà chưa giải quyết độ chính xác.

**2. CPU profiler thu 10 giây, không thấy method nghi ngờ. Có thể loại trừ method?**

Không. Cần biết workload nghi ngờ đã chạy trong 10 giây đó không, profiler dùng CPU hay wall-clock sampling, số mẫu hợp lệ, method có bị lọc hay bị chờ lock/I/O. Lấy lại profile bao trùm giai đoạn liên quan rồi đối chiếu metrics.

**3. Alert bắn lúc 10:30, kỹ sư bật JFR lúc 10:33 và thấy bình thường. Có thể nói JVM lúc 10:30 ổn không?**

Không. JFR vừa bật không chứa dữ liệu trước 10:33. Cần metrics/logs/traces đã được lưu từ 10:30 hoặc một rolling recording giữ lại lịch sử; nếu không có, ghi “thiếu bằng chứng thời điểm sự cố”.

**4. Counter tăng từ 9.000 lên 9.500 nhưng collection gap dài 100 giây. Có thể suy ra 500 sự kiện chỉ xảy ra tại giây cuối không?**

Không. Chênh lệch 500 chỉ cho biết tổng tăng giữa hai lần đo (nếu không reset); tốc độ trung bình của khoảng là `5 events/s`, không khôi phục được thời điểm cụ thể nếu thiếu timestamps/events.

**5. So sánh throughput trước và sau rollout thế nào để ít bị đánh lừa?**

Ghi `t_change`, cửa sổ warm-up, số request, traffic mix, route, instance count và cùng định nghĩa metric. Chọn cửa sổ trước/sau đủ dài bao trùm chu kỳ tải nhưng không trộn giai đoạn thay đổi, rồi kiểm tra error rate, saturation và latency distribution cùng lúc. Nếu không có kiểm soát tải, gọi kết quả là *tương quan quan sát được* thay vì chứng minh rollout là nguyên nhân.

## 13. Kết luận thực hành

Chọn **khoảng lấy mẫu** từ độ dài của tín hiệu cần bắt và kiểu dữ liệu được đo; chọn **thời lượng quan sát** để đủ cơ hội và số mẫu đại diện; chọn **cửa sổ sự cố** để giữ cả baseline, incident và recovery. Khi báo cáo, luôn ghi thời gian thực tế, nguồn, aggregation, sampling, gaps và mức overhead. Phép đo đáng tin cậy là phép đo **đúng thời điểm, đúng hiện tượng và đủ dữ liệu để kiểm chứng giả thuyết** — không đơn thuần là phép đo có nhiều điểm nhất.

### Tài liệu tham khảo

- [Oracle JDK 21 — `jcmd` diagnostic commands](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): `JFR.start`, `JFR.dump`, `JFR.stop`, `maxage`, `maxsize` và quyền attach.
- [OpenTelemetry — Metrics Data Model](https://opentelemetry.io/docs/specs/otel/metrics/data-model/): gauge/sum/histogram, timestamps, aggregation temporality và số observation.
- [Prometheus — Histograms and Summaries](https://prometheus.io/docs/practices/histograms/): percentile estimation, aggregation và ý nghĩa của rate.
