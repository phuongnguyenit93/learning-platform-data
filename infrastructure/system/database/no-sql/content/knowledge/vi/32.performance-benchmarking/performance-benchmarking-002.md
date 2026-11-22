# Phân vị p50/p95/p99 và giới hạn của giá trị trung bình

## 1. Tình huống mở đầu: trung bình 40 ms nhưng người dùng vẫn thấy ứng dụng “đơ”

Một API Java đọc danh sách đơn hàng từ cơ sở dữ liệu NoSQL. Dashboard hiển thị:

```text
GET /orders
Average latency = 40 ms
Throughput       = 2.000 req/s
Success rate     = 99,8%
```

Nhóm phát triển cho rằng hiệu năng rất tốt vì 40 ms thấp hơn mục tiêu 200 ms. Tuy nhiên, người dùng vẫn báo rằng một số yêu cầu mất hơn hai giây.

Khi xem phân bố độ trễ, nhóm nhận thấy:

```text
p50 =   12 ms
p95 =   90 ms
p99 =  850 ms
max = 3200 ms
```

Không có mâu thuẫn: **giá trị trung bình mô tả mức trung tâm theo tổng, còn các phân vị thể hiện phần đuôi của phân bố**. Một tỷ lệ nhỏ yêu cầu cực chậm vẫn có thể gây trải nghiệm tồi, làm gateway timeout và kích hoạt retry dây chuyền.

Bài học này giải thích cách hiểu, tính, đo và sử dụng **p50, p95, p99** khi tối ưu cơ sở dữ liệu NoSQL. Mục tiêu không phải “chọn phân vị càng cao càng tốt”, mà là hiểu chính xác câu hỏi mỗi thước đo trả lời, tránh bẫy thống kê và liên hệ kết quả với nguyên nhân vận hành.

## 2. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **latency, throughput, concurrency, error rate** và **freshness**.
2. Tính p50/p95/p99 theo một định nghĩa quantile được công bố.
3. Giải thích ý nghĩa “99% thao tác không chậm hơn ngưỡng p99” và phần 1% còn lại.
4. Nhận diện khi trung bình, min/max, p50 hoặc p95 che giấu sự cố.
5. Hiểu cách số mẫu, thời gian đo, sampling và nội suy ảnh hưởng quantile.
6. Phân biệt **percentile của thành công** với độ trễ mà người dùng thực sự quan sát.
7. Tránh tính p99 toàn hệ bằng cách lấy trung bình p99 của từng node.
8. Chọn histogram, HDR Histogram, t-digest hoặc phác thảo quantile phù hợp với mục tiêu.
9. Dùng Micrometer/Prometheus để quan sát độ trễ có ngữ cảnh.
10. Xây thử nghiệm NoSQL tái lập có baseline, warmup, tải đều/burst, cache và trạng thái phân tán.
11. Nhận diện coordinated omission, queueing, hot partition, compaction và retry amplification.
12. Diễn giải kết quả thành SLO, kế hoạch tối ưu và quyết định capacity.

## 3. Latency, throughput và concurrency là ba đại lượng khác nhau

**Latency** là thời gian để một thao tác hoàn tất theo điểm bắt đầu và kết thúc đã xác định, ví dụ từ lúc API nhận request đến khi trả response.

**Throughput** là số thao tác xử lý mỗi đơn vị thời gian, ví dụ 2.000 requests/giây.

**Concurrency** là số thao tác đang tồn tại đồng thời, bao gồm cả những thao tác đang chờ.

Ví dụ:

```text
Throughput:     2.000 req/s
Mean latency:      40 ms = 0,04 s
```

Trong hệ ổn định và đo trên phạm vi nhất quán, định luật Little cho trực giác:

\[
L=\lambda W
\]

Với \(\lambda=2.000\) req/s và \(W=0,04\) s:

\[
L\approx80\text{ requests đang tồn tại}
\]

Đây là quan hệ trung bình của hệ ổn định, **không phải cách tính p99**. Concurrency tức thời có thể cao hơn nhiều khi burst hoặc queue xuất hiện.

### 3.1. Đo ở đâu quyết định ý nghĩa

Một yêu cầu có thể trải qua:

```text
Client
  -> API gateway queue
  -> Java service
  -> MongoDB driver connection-pool wait
  -> Network
  -> Database execution
  -> Serialization
  -> Response
```

`db server duration = 10 ms` và `HTTP duration = 500 ms` đều có thể đúng. Nếu không định nghĩa điểm bắt đầu/kết thúc, không thể so hai số đó một cách có ý nghĩa.

## 4. Trung bình cộng là gì?

Với \(n\) quan sát độ trễ \(x_1,x_2,\ldots,x_n\):

\[
\bar{x}=\frac{1}{n}\sum_{i=1}^{n}x_i
\]

Ví dụ:

```text
Latencies (ms):
10, 10, 10, 10, 10, 10, 10, 10, 10, 110
```

Tổng là 200 ms, nên:

\[
\bar{x}=200/10=20\text{ ms}
\]

Nhưng **9 trong 10 requests chỉ mất 10 ms**, còn một request mất 110 ms. Trung bình 20 ms không thể hiện rõ request cực chậm đó.

### 4.1. Điểm mạnh của mean

- Dễ hiểu và dễ tính.
- Có quan hệ với tổng thời gian tiêu thụ và trung bình workload.
- Có thể gộp chính xác qua các nhóm nếu giữ **tổng thời gian và số mẫu**, không chỉ mean.
- Có thể hữu ích cho capacity và hiệu suất chung.

### 4.2. Giới hạn của mean

- Dễ bị ảnh hưởng bởi outlier cực lớn.
- Không chỉ ra tỷ lệ request vượt ngưỡng người dùng quan tâm.
- Hai phân bố rất khác nhau có thể có cùng mean.
- Không cho biết latency của request bất kỳ ở phần đuôi.
- Có thể bị đánh lừa khi hệ bỏ sót requests timeout hoặc chỉ đo operations thành công.

**Mean không sai; sai là dùng mean để trả lời câu hỏi về tail latency.**

## 5. Percentile/quantile là gì?

**Phân vị p** (percentile) mô tả một ngưỡng trong phân bố dữ liệu. Ví dụ:

- **p50:** một ngưỡng mà khoảng 50% các quan sát không lớn hơn nó; thường gọi median.
- **p95:** ngưỡng ứng với khoảng 95% quan sát.
- **p99:** ngưỡng ứng với khoảng 99% quan sát.

Với một tập mẫu hữu hạn, cách chọn ngưỡng phụ thuộc định nghĩa quantile và quy tắc nội suy. Khi nói **p99 = 500 ms**, cách hiểu vận hành thường là khoảng 99% operations nằm ở hoặc dưới mức này trong **mẫu, cửa sổ thời gian và phạm vi đo đã nêu**.

### 5.1. Không nên diễn giải ngược

Nếu p99 = 500 ms:

- **Không** có nghĩa mọi request đều dưới 500 ms.
- **Không** có nghĩa request chậm nhất là 500 ms.
- **Không** nói latency trung bình là 500 ms.
- **Không** đảm bảo 99% tất cả requests trong tương lai đều dưới 500 ms.
- **Không** mô tả riêng error rate, data correctness hoặc replication freshness.
- **Không** chứng minh 1% còn lại chỉ chậm hơn một chút.

Một request trong phần đuôi có thể là 501 ms hoặc 30 giây, tùy phân bố.

## 6. Cách tính theo nearest-rank

Để thống nhất trong các ví dụ của bài, dùng **nearest-rank quantile** với \(0<p\le1\).

1. Sắp xếp \(n\) độ trễ theo thứ tự tăng.
2. Tính vị trí:

\[
k=\lceil p\cdot n\rceil
\]

3. Lấy phần tử thứ \(k\), tính từ 1.

Ví dụ dãy 10 giá trị đã sắp:

```text
10, 10, 10, 10, 10, 10, 10, 10, 10, 110
```

- p50: \(k=\lceil0,50\times10\rceil=5\) → 10 ms.
- p95: \(k=\lceil0,95\times10\rceil=10\) → 110 ms.
- p99: \(k=\lceil0,99\times10\rceil=10\) → 110 ms.

### 6.1. Vì sao một công cụ có thể cho số khác?

Các thư viện có thể dùng phương pháp nội suy, ví dụ liên kết vị trí \((n-1)p\) giữa hai phần tử. Với mẫu nhỏ, p95 hoặc p99 khác nearest-rank đáng kể.

Không có lý do coi một số nội suy và một số nearest-rank là “một bên chắc chắn tính sai”. Cần công bố **thuật toán, quy tắc mẫu, aggregation và error bound** trước khi so sánh.

### 6.2. Phải xử lý trường hợp \(p=0\)

Với nearest-rank, công thức trên dành cho \(p>0\). Nếu cần p0, định nghĩa riêng là minimum; p100 thường tương ứng maximum trong tập mẫu hữu hạn. Không dùng `index=-1` hoặc truy cập ngoài mảng khi p=0.

## 7. Ví dụ 100 requests và một outlier rất lớn

Giả sử:

| Nhóm | Số requests | Latency |
| --- | ---: | ---: |
| Nhanh | 95 | 10 ms |
| Trung bình | 4 | 100 ms |
| Rất chậm | 1 | 5.000 ms |

Mean:

\[
\bar{x}=
\frac{95\times10+4\times100+1\times5.000}{100}
=63,5\text{ ms}
\]

Theo nearest-rank:

```text
p50  = 10 ms
p95  = 10 ms
p99  = 100 ms
p100 = 5000 ms
```

Bài học quan trọng:

- Mean 63,5 ms **cao hơn nhiều** p50 do một outlier.
- p95 là 10 ms vì đúng 95 requests ở 10 ms.
- p99 là 100 ms, **vẫn không phản ánh request chậm nhất**.
- p99 là số liệu quan trọng, nhưng không phải toàn bộ sự thật.

Để thấy sự cố ảnh hưởng 0,1% requests, có thể cần p99.9 hoặc **count vượt ngưỡng**, tùy số mẫu và độ tin cậy.

## 8. Hai hệ có cùng mean nhưng trải nghiệm khác nhau

Hệ A:

```text
100 requests, mỗi request 100 ms
Mean = 100 ms
p50 = p95 = p99 = 100 ms
```

Hệ B:

```text
99 requests, mỗi request 10 ms
1 request, 9010 ms
Mean = (99*10 + 9010)/100 = 100 ms
p50 = 10 ms
p95 = 10 ms
p99 = 10 ms
max = 9010 ms
```

Hai hệ có cùng **mean = 100 ms**, nhưng:

- A ổn định, không có request quá chậm.
- B rất nhanh ở đa số requests nhưng 1% trải nghiệm cực kỳ tệ.
- p99 nearest-rank của B còn chưa phản ánh outlier vì request cực chậm rơi ở vị trí 100.

Vì vậy một báo cáo chỉ có mean và p99 cũng có thể thiếu thông tin. Cần xem **p99.9, maximum, count > threshold, timeout rate và biểu đồ phân bố** khi tail nghiêm trọng.

## 9. p50, p95 và p99 phù hợp với câu hỏi nào?

| Chỉ số | Câu hỏi hữu ích | Giới hạn |
| --- | --- | --- |
| Mean | Độ trễ trung bình của các mẫu? | Bị outlier chi phối |
| p50 | Request điển hình mất bao lâu? | Che phần đuôi |
| p90 | Phần lớn requests đã nhanh chưa? | Không thấy 10% chậm nhất rõ |
| p95 | 5% chậm nhất có biểu hiện ra sao tại ngưỡng? | Chưa mô tả độ sâu phần đuôi |
| p99 | 1% đuôi bắt đầu ở đâu? | Không mô tả 1% chậm hơn ngưỡng |
| p99.9 | Phần đuôi rất hiếm? | Cần mẫu lớn và đo cẩn thận |
| Max | Request tệ nhất được ghi nhận? | Rất nhạy với một mẫu, không ổn định |
| Error/timeout rate | Bao nhiêu thao tác thất bại? | Không mô tả độ trễ thành công |
| Threshold exceedance | Bao nhiêu thao tác vượt X ms? | Chỉ trả lời ngưỡng X |
| Throughput/QPS | Xử lý bao nhiêu thao tác? | Không đảm bảo latency/correctness |

### 9.1. Nên xem bộ chỉ số

Với API quan trọng:

```text
Throughput / arrival rate
Success, error, timeout rate
Mean and p50/p95/p99 latency
Count above SLO threshold
Concurrency / queue wait
Database server and client duration
Consistency and correctness indicators
```

Nếu chỉ tối ưu một chỉ số, hệ có thể đẹp ở dashboard nhưng kém trên những chiều còn lại.

## 10. Một phân vị là kết quả của một tập mẫu cụ thể

Bất kỳ phát biểu “p99 = 300 ms” nào cũng cần trả lời:

```text
Phạm vi:        HTTP POST /orders
Môi trường:     production, region A
Khoảng thời gian: 5 phút
Các mẫu:       requests kết thúc trong cửa sổ
Bao gồm:       success + những terminal failures có duration
Loại trừ:      health checks
Số mẫu:        60.000
Đơn vị:        millisecond
Công cụ:       histogram backend / query
```

Nếu không biết scope, so sánh có thể sai:

- p99 server execution với p99 HTTP end-to-end.
- p99 chỉ thành công với p99 mọi request.
- p99 giờ thấp điểm với p99 flash sale.
- p99 MongoDB query với p99 Redis HIT.
- p99 một vùng với p99 nhiều vùng.
- p99 100 mẫu với p99 1 triệu mẫu.

**Phân vị không có ý nghĩa đầy đủ khi thiếu population và thời gian đo.**

## 11. Cửa sổ thời gian thay đổi câu chuyện

Giả sử API có 55 phút bình thường, 5 phút rất chậm do compaction.

Nếu tính p99 **toàn giờ**, giai đoạn lỗi ngắn có thể bị “pha loãng” tùy lượng request. Nếu tính p99 mỗi 1 phút, spike nổi bật hơn.

Ngược lại, khi traffic quá thấp, p99 mỗi phút có thể chỉ từ vài requests và dao động mạnh.

### 11.1. Chọn cửa sổ theo mục đích

- 1 phút: phát hiện spike ngắn, nhưng dễ nhiễu với traffic thấp.
- 5 phút: thường phù hợp dashboard vận hành.
- 30–60 phút: xem xu hướng rộng hơn.
- Nhiều ngày: capacity/seasonality và review SLO dài hạn.

Các khoảng trên là ví dụ, không phải quy tắc bắt buộc.

### 11.2. Rolling window và fixed window

Một rolling window luôn xét một khoảng trượt; fixed window phân đoạn theo mốc cố định. Sự khác biệt có thể tạo hai đồ thị khác nhau cùng thời điểm.

Đặt chú thích aggregation/window trong dashboard để người xem không so số liệu khác ngữ nghĩa.

## 12. Số lượng mẫu: tại sao p99 khó ổn định với tải thấp?

Nếu n = 100 và dùng nearest-rank:

```text
p99 = phần tử thứ 99
```

Chỉ một vài quan sát ở phần đuôi có thể khiến kết quả thay đổi mạnh.

Nếu n = 1.000:

```text
p99 = phần tử thứ 990
```

Nhóm 1% cuối có khoảng 10 quan sát.

Nếu n = 100.000, phần 1% cuối có khoảng 1.000 quan sát — cung cấp bức tranh phong phú hơn, nhưng **samples có thể tương quan**, ví dụ cùng một sự cố làm chậm mọi request trong 3 giây.

### 12.1. Không có “tối thiểu 100 mẫu là p99 đáng tin”

Ước lượng phân vị phụ thuộc:

- Số lượng mẫu.
- Phân bố ở vùng đuôi.
- Mức độ tương quan theo thời gian và theo key.
- Sampling bias.
- Phương pháp histogram/sketch.
- Sai số và mức tin cậy mong muốn.

Với p99.9, cần đặc biệt thận trọng. Một vài requests bất thường không đủ để suy độ trễ phần nghìn bền vững.

### 12.2. Khi số mẫu nhỏ

Ngoài p95/p99, báo:

```text
n = 37
max = ...
number > 500 ms = ...
min/median = ...
```

Điều đó giúp người đọc biết độ chắc chắn của ước lượng, thay vì nói “p99 tăng 80%” trên vài request.

## 13. Sampling làm thay đổi phân bố nếu chọn sai

Giả sử dịch vụ xử lý 1 triệu requests nhưng chỉ log 1% vì lý do chi phí.

Nếu sampling ngẫu nhiên, độc lập với latency, quantile từ mẫu vẫn có uncertainty.

Nếu chỉ log requests thành công hoặc chỉ log requests chậm:

- Phân bố quan sát sẽ **lệch**.
- Không thể áp kết quả trực tiếp cho toàn traffic.
- Cần biết sampling rule và trọng số nếu có.

### 13.1. Head-based trace sampling

Chọn trace trước khi biết nó sẽ chậm hay nhanh. Nếu chỉ lấy 0,1%, p99 trong những traces ấy có thể thiếu mẫu.

### 13.2. Tail-based trace sampling

Giữ nhiều traces chậm/lỗi sau khi biết outcome. Rất hữu ích để **điều tra**, nhưng không tính p99 traffic bằng cách lấy thẳng những traces đã được ưu tiên giữ.

### 13.3. Metrics và traces có vai trò khác

Metrics histogram không nên phụ thuộc vào tập traces sampled nếu mục tiêu là độ trễ toàn traffic. Instrument counter/timer ở đúng boundary, còn traces làm nguồn giải thích những trường hợp tiêu biểu.

## 14. Lỗi lớn nhất: chỉ đo latency của thao tác thành công

Giả sử có 100 requests:

```text
95 requests thành công trong 50 ms
5 requests timeout sau 10.000 ms
```

Nếu code ghi Timer **chỉ khi success**:

```text
Observed p99 successes = 50 ms
```

Dashboard cho cảm giác rất tốt trong khi 5% người dùng đợi 10 giây rồi nhận lỗi.

### 14.1. Cần tách ba phép đo

1. **Duration của toàn bộ requests hoàn tất**, bao gồm failure.
2. **Duration theo outcome**, ví dụ success, timeout, rejected, cancelled.
3. **Outcome rate**, đặc biệt timeout/unknown commit.

Một request timeout trước khi database trả lời không nhất thiết đồng nghĩa database chưa commit. Metrics nên phân biệt `TIMEOUT_UNKNOWN` với `CONDITION_REJECTED` hoặc `VALIDATION_REJECTED`.

### 14.2. Timeout là dữ liệu bị kiểm duyệt (censoring)

Nếu client dừng chờ ở 2 giây, request thực tế có thể hoàn tất ở server sau 2,1 giây hoặc 20 giây — client không biết đầy đủ.

Ghi 2.000 ms cho timeout là hợp lý khi đo **thời gian client đã chờ**, nhưng không phải bằng chứng server execution thực sự chỉ kéo dài 2.000 ms.

Một báo cáo đầy đủ phải giữ timeout count/unknown outcomes, thay vì diễn giải censored observations như latency hoàn tất bình thường.

### 14.3. Cancelled requests

Nếu người dùng hủy sau 100 ms, duration client thấy là 100 ms nhưng server có thể vẫn đang chạy. Cần định nghĩa rõ population trong từng metric và xử lý cancellation propagation.

## 15. Percentiles không cộng được qua các tầng

Một request có:

```text
API gateway
  -> Application
      -> Redis
      -> MongoDB
      -> Serialization
```

Một lỗi phân tích phổ biến:

```text
Gateway p99    = 30 ms
MongoDB p99    = 80 ms
Application p99= 50 ms
Total p99      = 160 ms   <-- kết luận không hợp lệ
```

**p99 của các thành phần không cộng được** để suy p99 của tổng vì các giá trị ở phân vị đó có thể thuộc **những requests khác nhau** và có tương quan khác nhau.

### 15.1. Thay thế

- Đo trực tiếp Timer ở điểm bắt đầu/kết thúc end-to-end.
- Với một request cụ thể, dùng trace để xem critical path và thời gian từng span.
- Với hệ thống, dùng histogram cho từng tầng và end-to-end trên populations phù hợp.
- Phân biệt operations chạy song song: end-to-end wall time không bằng tổng durations của mọi child spans.

## 16. Không lấy trung bình p99 các nodes/shards

Giả sử:

| Node | Requests | p99 |
| --- | ---: | ---: |
| A | 100 | 500 ms |
| B | 100.000 | 20 ms |

Tính:

\[
(500+20)/2=260\text{ ms}
\]

**không** cho ra p99 toàn hệ. Node B có lượng traffic lớn hơn 1.000 lần, và phân bố mỗi node không được mô tả đầy đủ chỉ bằng một số p99.

### 16.1. Trung bình có trọng số của p99 cũng không đúng

Thử:

\[
\frac{100\times500+100.000\times20}{100.100}
\]

vẫn không phải p99 toàn hệ. Quantiles là thống kê **không tuyến tính**; không thể phục dựng phân bố chung từ quantile đơn lẻ và sample counts.

### 16.2. Cách gộp đúng hơn

- Giữ raw observations nếu volume nhỏ và chính sách cho phép.
- Hoặc gộp **histogram bucket counts** cùng ranh giới bucket.
- Hoặc merge sketches được thiết kế hỗ trợ merge.
- Sau đó tính p99 từ phân bố gộp hoặc ước lượng của nó.

Nếu hai histograms có bucket boundaries không tương thích, không cộng bừa rồi gọi là global p99.

## 17. Simpson's paradox: tổng thể tốt hơn dù nhóm quan trọng xấu đi

Giả sử baseline và sau triển khai có hai loại request:

| Trước deploy | Số lượng | Mean |
| --- | ---: | ---: |
| Cache HIT | 900 | 10 ms |
| Cache MISS | 100 | 200 ms |

Sau deploy:

| Sau deploy | Số lượng | Mean |
| --- | ---: | ---: |
| Cache HIT | 9.900 | 12 ms |
| Cache MISS | 100 | 250 ms |

Ở **cả hai nhóm** latency đều xấu hơn: HIT từ 10 lên 12 ms, MISS từ 200 lên 250 ms.

Nhưng mean chung:

Trước deploy:

\[
(900\times10+100\times200)/1000=29\text{ ms}
\]

Sau deploy:

\[
(9900\times12+100\times250)/10000=14,38\text{ ms}
\]

Mean tổng thể **trông tốt hơn** do tỷ trọng HIT tăng rất mạnh. Đây là ví dụ trực giác về lỗi suy luận từ dữ liệu gộp khi **workload mix thay đổi**.

### 17.1. Phân vị cũng bị ảnh hưởng bởi mix

Không chỉ mean: p95/p99 toàn hệ có thể tăng hoặc giảm do tỷ lệ GET/UPDATE, cache HIT/MISS, region hoặc tenant tier thay đổi.

Muốn so hiệu năng của một thay đổi, cần:

- So cùng operation/query shape.
- So cùng workload distribution hoặc chuẩn hóa mix.
- Kiểm tra cả số tổng và số theo nhóm.
- Nêu tỷ lệ traffic ở mỗi nhóm.

## 18. Quantile từ dữ liệu thô bằng Java

Một cách tính nearest-rank cho tập mẫu nhỏ:

```java
import java.util.Arrays;

public final class Percentiles {
    private Percentiles() {}

    public static long nearestRank(long[] observations, double p) {
        if (observations == null || observations.length == 0) {
            throw new IllegalArgumentException("Empty observations");
        }
        if (!(p > 0.0 && p <= 1.0)) {
            throw new IllegalArgumentException("p must be in (0,1]");
        }

        long[] sorted = observations.clone();
        Arrays.sort(sorted);

        int rank = (int) Math.ceil(p * sorted.length);
        int index = Math.max(0, Math.min(rank - 1, sorted.length - 1));
        return sorted[index];
    }

    public static double mean(long[] observations) {
        if (observations == null || observations.length == 0) {
            throw new IllegalArgumentException("Empty observations");
        }

        double sum = 0.0;
        for (long sample : observations) {
            sum += sample;
        }
        return sum / observations.length;
    }

    public static void main(String[] args) {
        long[] latenciesMs = {
            10, 10, 10, 10, 10, 10, 10, 10, 10, 110
        };

        System.out.println("mean=" + mean(latenciesMs));
        System.out.println("p50=" + nearestRank(latenciesMs, 0.50));
        System.out.println("p95=" + nearestRank(latenciesMs, 0.95));
        System.out.println("p99=" + nearestRank(latenciesMs, 0.99));
    }
}
```

Kết quả dự kiến:

```text
mean=20.0
p50=10
p95=110
p99=110
```

### 18.1. Giới hạn của code

- Copy và sort toàn bộ dữ liệu: \(O(n\log n)\) thời gian, \(O(n)\) bộ nhớ bổ sung.
- Không thích hợp giữ mọi observation liên tục cho traffic rất lớn.
- Đây là **nearest-rank**, không nhất thiết giống Excel, NumPy, Prometheus hoặc công cụ APM.
- Chưa cung cấp confidence interval.
- Không lọc dữ liệu bất thường hay negative durations; caller phải đảm bảo đơn vị/semantics.
- Không dùng `System.currentTimeMillis()` để đo elapsed time trong một request khi có monotonic clock.

## 19. JUnit test cho quantile

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

public class PercentilesTest {
    @Test
    void exampleNearestRank() {
        long[] x = {
            10, 10, 10, 10, 10, 10, 10, 10, 10, 110
        };

        assertEquals(10, Percentiles.nearestRank(x, 0.50));
        assertEquals(110, Percentiles.nearestRank(x, 0.95));
        assertEquals(110, Percentiles.nearestRank(x, 0.99));
        assertEquals(20.0, Percentiles.mean(x), 0.0001);
    }

    @Test
    void doesNotMutateInput() {
        long[] x = {200, 10, 30};
        Percentiles.nearestRank(x, 0.50);
        assertArrayEquals(new long[]{200, 10, 30}, x);
    }

    @Test
    void rejectsEmptyInput() {
        assertThrows(IllegalArgumentException.class,
            () -> Percentiles.nearestRank(new long[0], 0.99));
    }
}
```

Test này xác minh thuật toán thử nghiệm, **không phải benchmark hiệu năng driver NoSQL**.

## 20. Đo thời gian trong Java: dùng monotonic elapsed time

Với một thao tác trong cùng JVM:

```java
long start = System.nanoTime();
try {
    return repository.loadOrder(orderId);
} finally {
    long elapsedNanos = System.nanoTime() - start;
    // Ghi Timer/Histogram theo đúng boundary.
}
```

`System.nanoTime()` phù hợp để đo duration trong một process. Giá trị tuyệt đối của nó không phải Unix timestamp và không so trực tiếp giữa hai hosts.

### 20.1. Không dùng wall clock để đo elapsed khi có thể tránh

`Instant.now()` và `System.currentTimeMillis()` phục vụ thời gian lịch; clock có thể được điều chỉnh. Nếu lấy hiệu hai lần đọc wall clock, duration có thể bị ảnh hưởng bởi clock jump.

### 20.2. Định nghĩa bắt đầu và kết thúc

Ví dụ:

```text
Service timer:
  start trước khi gọi repository
  stop sau khi xử lý result/error

Driver timer:
  start khi command gửi tới transport
  stop khi response/terminal error nhận

Server timer:
  do engine đo từ lúc tiếp nhận command
  tới khi xử lý theo semantics của engine
```

Chỉ số khác nhau có thể hợp lệ; đặt tên đừng khiến người đọc tưởng chúng cùng phạm vi.

## 21. Histogram: lưu phân bố mà không giữ từng request

Một histogram chia durations vào các buckets:

| Bucket giới hạn trên | Số quan sát không vượt ngưỡng (cumulative) |
| --- | ---: |
| 10 ms | 200 |
| 25 ms | 580 |
| 50 ms | 900 |
| 100 ms | 970 |
| 250 ms | 990 |
| 500 ms | 995 |
| +Inf | 1000 |

Với cumulative histogram:

- Bucket `le=100ms` có 970 mẫu.
- Bucket `le=250ms` có 990 mẫu.
- Tổng là 1.000 mẫu.

Như vậy ngưỡng p99 rơi gần **bucket 250 ms**. Công cụ thường nội suy trong bucket theo một mô hình; độ chính xác phụ thuộc bucket boundaries và phân bố bên trong bucket.

### 21.1. Bucket không phải giá trị p99 chính xác

Nếu 20 samples nằm trong khoảng 100–250 ms, histogram không biết chính xác từng giá trị. Không thể suy p99 chính xác đến microsecond khi bucket rộng 150 ms.

### 21.2. Chọn buckets theo SLO

Nếu SLO ở 200 ms, nên có những boundaries đủ gần 200 ms để đánh giá breach. Một bucket từ 100 ms đến 1 s sẽ quá thô.

### 21.3. Histogram có thể gộp

Các cumulative bucket counts có cùng boundaries và cùng đơn vị có thể cộng theo service/instance/region để ước lượng quantile toàn hệ, miễn là các mẫu thuộc đúng population và không đếm trùng.

## 22. HDR Histogram, t-digest và DDSketch

Khi traffic lớn, có nhiều cấu trúc tóm tắt phân bố.

| Cấu trúc | Điểm mạnh | Điểm cần kiểm tra |
| --- | --- | --- |
| Fixed histogram | Dễ gộp bucket; phổ biến trong Prometheus | Sai số phụ thuộc buckets |
| HDR Histogram | Hiệu quả cho dải độ trễ rộng với độ chính xác tương đối có cấu hình | Range/sig-digits, merge semantics |
| t-digest | Có thể ước lượng quantile, thường chú trọng tails | Sai số theo phân bố/implementation |
| DDSketch | Ước lượng theo giới hạn sai số tương đối tùy cấu hình | Mapping, merge, memory |
| Raw observations | Tính chính xác theo thuật toán chọn | Tốn bộ nhớ/chi phí |
| Summary client-side quantile | Tiện cho một process/window | Không gộp quantile trực tiếp |

### 22.1. Không có sketch “chính xác tuyệt đối” miễn phí

Mọi cấu trúc có trade-off:

- Memory.
- Sai số ở p99/p99.9.
- Dải hỗ trợ.
- Mergeability.
- Tốc độ update.
- Sự ổn định qua restart/window.
- Khả năng truy vấn threshold.

Chọn theo SLO và điều cần quyết định, không chọn chỉ vì benchmark nội bộ quảng cáo latency rất thấp.

### 22.2. Kiểm tra coordinated omission của recorder

Một thư viện histogram có thể hỗ trợ ghi bù các mẫu bị bỏ sót khi nguồn đo bị pause theo một expected interval. Nhưng kỹ thuật đó chỉ hợp lý khi **mô hình arrival và khoảng dự kiến phù hợp**; không tùy ý “bù” dữ liệu cho mọi workload.

## 23. Micrometer Timer trong Java

Micrometer có `Timer` và registry để đo duration.

Ví dụ:

```java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import java.util.concurrent.Callable;

public final class NoSqlTimer {
    private final MeterRegistry registry;

    public NoSqlTimer(MeterRegistry registry) {
        this.registry = registry;
    }

    public <T> T record(
            String operation,
            Callable<T> action
    ) throws Exception {

        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";

        try {
            return action.call();
        } catch (Exception ex) {
            outcome = classify(ex);
            throw ex;
        } finally {
            Timer timer = Timer.builder("app.nosql.operation.duration")
                .description("Application-observed NoSQL call duration")
                .tag("operation", operation)
                .tag("outcome", outcome)
                .publishPercentileHistogram()
                .register(registry);

            sample.stop(timer);
        }
    }

    private String classify(Exception ex) {
        // Trong production: ánh xạ sang tập enum hữu hạn.
        return "error";
    }
}
```

Ý nghĩa:

- Dùng `finally` để ghi cả các lời gọi ném exception.
- `operation` phải thuộc danh sách cố định, ví dụ `findOrder`, `reserveStock`.
- `outcome` cần phân biệt các loại terminal results/unknown như policy.
- Thời gian đo bao cả chờ client/pool/network/retry nếu những phần đó nằm trong `action.call()`.
- Histogram được cấu hình để exporter có thể hỗ trợ aggregate.

### 23.1. Không đăng ký hàng triệu meters

Nếu `operation` bằng raw query string hoặc `orderId`, số meters tăng vô hạn. Không dùng raw business IDs trong labels.

### 23.2. Không đo hai lần mà không đặt tên rõ

Có thể có một timer HTTP và một timer NoSQL lồng nhau. Điều đó đúng, nhưng **không cộng số samples của hai timers** để suy số HTTP requests.

## 24. Prometheus: tính p99 từ histogram buckets

Giả sử exporter có classic histogram:

```text
app_nosql_operation_duration_seconds_bucket
app_nosql_operation_duration_seconds_count
app_nosql_operation_duration_seconds_sum
```

Một truy vấn minh họa:

```promql
histogram_quantile(
  0.99,
  sum by (le, operation) (
    rate(app_nosql_operation_duration_seconds_bucket[5m])
  )
)
```

p95 tương tự:

```promql
histogram_quantile(
  0.95,
  sum by (le, operation) (
    rate(app_nosql_operation_duration_seconds_bucket[5m])
  )
)
```

Giá trị ví dụ tính **giây** nếu metric duration được export theo seconds.

### 24.1. Vì sao phải giữ label `le`?

Với classic histogram, `le` là ranh giới bucket. Bỏ `le` khi sum làm mất thông tin cần cho `histogram_quantile`.

### 24.2. Native histograms khác classic histograms

Prometheus hỗ trợ các dạng histogram khác nhau theo version/config. Query và phép aggregate có thể khác. Các ví dụ trên dành cho **classic `_bucket` series**; phải xem định dạng exporter thực tế.

### 24.3. Đừng cộng histogram của operations khác nhau khi so SLO

Nếu `findById` p99 rất nhanh nhưng `aggregateReport` p99 rất chậm, một p99 gộp có thể không đại diện cho bất kỳ hành trình người dùng nào. Chỉ gộp khi populations và SLO có ý nghĩa chung.

## 25. Đo tỷ lệ request vượt ngưỡng 200 ms

Đôi khi câu hỏi SLO rõ hơn là:

> “Trong 5 phút vừa qua, bao nhiêu phần trăm requests vượt 200 ms?”

Nếu histogram có bucket `le="0.2"`:

```promql
1 -
(
  sum(rate(app_nosql_operation_duration_seconds_bucket{le="0.2"}[5m]))
  /
  sum(rate(app_nosql_operation_duration_seconds_count[5m]))
)
```

Điều kiện: tất cả buckets và counts cùng scope, histogram có boundary 0.2 và denominator không bằng 0. Nếu muốn tính **toàn bộ user-visible requests**, hãy dùng timer ở HTTP boundary và kiểm tra population lỗi/timeout.

### 25.1. Vì sao threshold count hữu ích?

SLO “99% requests không vượt 200 ms” trực tiếp là:

\[
\frac{\text{requests}\le 200ms}{\text{total requests}}\ge0,99
\]

Đây có thể dễ kiểm tra hơn việc suy p99 từ bucket có độ phân giải thô.

### 25.2. Error budget

Nếu SLO cho phép 1% requests vượt ngưỡng hoặc lỗi theo định nghĩa service, 100.000 requests có ngân sách khoảng 1.000 “bad events” trong thời hạn đánh giá.

Định nghĩa “bad event” phải rõ: có tính `5xx`, timeout, cancellation, invalid response, stale data hay không? Không tự thay đổi denominator khi incident xảy ra.

## 26. Không nên tối ưu p99 một cách độc lập với error rate

Giả sử hệ A:

```text
p99 successful requests = 80 ms
error rate = 20%
```

Hệ B:

```text
p99 successful requests = 250 ms
error rate = 0,01%
```

Không thể kết luận A tốt hơn chỉ vì p99 thấp hơn. A đang trả lỗi cho quá nhiều người dùng; có thể những request chậm bị timeout và biến mất khỏi sample latency success.

### 26.1. Báo cáo nên nêu đồng thời

```text
Total attempts
Terminal outcomes
Success-rate/error-rate/timeout-rate
Latency end-to-end by outcome
Threshold exceedance rate
p50/p95/p99 successful latencies
Unknown write outcomes (nếu có)
```

### 26.2. Đừng tối ưu bằng fail-fast cho mọi request

Nếu hệ reject nhanh 30% traffic, p99 của những request còn được xử lý có thể rất đẹp. Một thay đổi chỉ hợp lệ nếu availability/admission policy và business SLO cho phép.

## 27. Queueing và hiện tượng p99 tăng đột ngột khi tải gần trần

Khi mức sử dụng tài nguyên gần 100%, queue wait có thể tăng mạnh dù mean service time không đổi.

Ví dụ:

```text
Source query service time trung bình: 10 ms
Concurrency/worker budget: 100
Arrival rate tăng từ vừa đủ sang gần trần
```

Khi traffic đến theo burst, queue có thể dài. Một số request:

```text
DB processing: 10 ms
Waiting in queue: 400 ms
Observed client latency: 410 ms
```

### 27.1. Không chỉ nhìn CPU

Bottleneck có thể là:

- Connection pool.
- Max in-flight requests.
- Hot partition.
- IOPS.
- Replica coordination.
- Network.
- Compaction/write stalls.
- Lock/transaction contention.
- Queue ở application/SDK.

CPU trung bình thấp không chứng minh hệ không bị saturation.

### 27.2. Dấu hiệu overload

- p50 còn tương đối ổn.
- p95/p99 tăng trước hoặc mạnh hơn p50.
- Pool wait và queue depth tăng.
- Retry/timeouts tăng.
- Throughput không tăng tương ứng với offered load.
- Recovery chậm sau khi burst kết thúc.

## 28. Open-loop và closed-loop load test

**Closed-loop**: một client gửi request, đợi response rồi mới gửi request tiếp theo.

```text
send -> wait -> send -> wait
```

**Open-loop**: load generator cố phát request theo lịch arrival rate độc lập với latency của requests trước.

```text
t=0ms    send
t=10ms   send
t=20ms   send
...
```

### 28.1. Vì sao khác nhau?

Nếu server stall 2 giây:

- Closed-loop client đang chờ sẽ **không gửi thêm** trong 2 giây.
- Open-loop load generator có thể tiếp tục tạo requests theo workload arrivals, khiến queue tăng.

Closed-loop có thể thích hợp mô phỏng số users với thời gian nghĩ/think time cụ thể; nhưng nếu muốn đo hệ trước một arrival process độc lập, closed-loop có thể che overload.

### 28.2. Offered load vs achieved throughput

Trong báo cáo cần tách:

```text
Target arrival rate: 5.000 req/s
Actually sent rate: 4.200 req/s
Completed throughput: 3.800 req/s
Timed out/rejected: ...
Outstanding queue: ...
```

Một generator bị nghẽn có thể không đạt target RPS. Nếu chỉ báo `completed throughput=3.800`, nhóm có thể hiểu sai rằng server được thử ở 5.000 req/s.

## 29. Coordinated omission: phép đo vô tình bỏ qua giai đoạn hệ chậm

Đây là bẫy quan trọng trong latency benchmarking.

Giả sử client đồng bộ luôn gửi request mới **sau** khi request trước hoàn tất. Khi server pause 3 giây, client không gửi thêm requests trong thời gian pause.

Kết quả:

```text
Một request ghi nhận latency 3 giây.
Hàng trăm arrivals lẽ ra xảy ra khi stall
không được gửi/ghi nhận.
```

Phân bố mẫu có thể thiếu nhiều user-visible waits mà arrival model thực phải gánh. p99 nhìn **tốt hơn** tình hình nếu traffic ngoài đời vẫn đến trong thời gian stall.

### 29.1. Cách khắc phục theo mô hình test

- Dùng open-loop load generator có khả năng giữ lịch arrivals.
- Ghi cả **scheduled send time** và actual send time, không chỉ duration từ lúc gửi thành công.
- Đo queueing/wait khi generator không bắt kịp.
- Dùng histogram correction chỉ khi phù hợp expected interval/model.
- Công bố policy của generator khi report p99.

### 29.2. Không mặc định open-loop luôn tốt hơn

Closed-loop có thể đúng nếu muốn mô hình hóa **một số client hữu hạn, mỗi client đợi và suy nghĩ trước lần gửi tiếp**. Vấn đề là chọn mô hình không khớp workload thực rồi diễn giải số p99 như phổ quát.

## 30. Warmup, JIT, connection pool và cache gây nhiễu

Trong Java/NoSQL, thời gian đầu có thể bao gồm:

- JVM startup và JIT compilation.
- Class loading/serialization codec initialization.
- DNS, TLS và authentication.
- Connection pool warmup.
- Prepared statements.
- Cache cold MISS.
- Server page cache chưa warm.
- Index/compaction background work.

### 30.1. Đo hai pha riêng

**Cold-start performance** cần đo những yếu tố trên nếu user thực sự gặp chúng.

**Steady-state performance** có thể chạy warmup rồi đo riêng, nhưng phải chỉ rõ thời gian warmup và tiêu chí ổn định.

Không bỏ cold-start latency khỏi báo cáo nếu hệ serverless/auto-scaling thường xuyên tạo instances mới.

### 30.2. Preload dữ liệu cũng có tác dụng phụ

Nếu chạy test warmup bằng cùng tập keys, toàn bộ working set có thể nằm trong Redis/page cache. Production traffic với hàng triệu keys khác sẽ có hit ratio thấp hơn.

Benchmark phải ghi dataset size, key popularity distribution và tỷ lệ HIT/MISS.

## 31. Query shape: p99 NoSQL không thuộc riêng database product

Với MongoDB, hai truy vấn:

```javascript
db.orders.find({
  tenantId: "T01",
  orderId: "O1001"
});
```

và:

```javascript
db.orders.find({
  status: "PAID"
}).sort({
  createdAt: -1
}).limit(1000);
```

có thể chạm những access paths rất khác nhau.

- Một truy vấn point lookup có index tốt có thể ổn định.
- Một query cần scan/sort có thể có tail latency cao do dữ liệu nhiều.
- Query phân tán across shards có thể bị ảnh hưởng bởi shard chậm nhất.

### 31.1. Group theo query fingerprint

Không tính p99 của cả hai rồi suy một index có vấn đề. Nên nhóm:

```text
db.system
operation type
collection/table
query shape fingerprint
routing pattern
consistency/read preference
result count band
```

### 31.2. Không log raw query values làm metric labels

Raw `tenantId`, user ID, search text hay order ID tạo cardinality rất lớn và có thể lộ PII. Query fingerprint nên giữ cấu trúc filter/sort/index shape nhưng chuẩn hóa giá trị.

## 32. MongoDB: lý do p99 có thể cao

Những nguyên nhân cần xem theo deployment:

- Collection scan hoặc index không phù hợp.
- Blocking sort/aggregation.
- Shard targeting sai gây scatter–gather.
- Hot shard hoặc jumbo/chênh lệch phân bố.
- Connection pool acquisition.
- Replica read lag và read preference.
- Transaction contention.
- Disk I/O và cache misses.
- Checkpoint/background operations.
- Document size/serialization.
- Retry hoặc server selection trong failover.

### 32.1. Phân biệt command duration và server execution

Mongo Java Driver command monitoring có thể đo thời gian command trong phạm vi driver. Application timer có thể bao thêm pool wait/retries; profiler/server diagnostics có scope khác.

Không kết luận “MongoDB xử lý 2 giây” từ HTTP span dài 2 giây mà không phân tích các tầng.

### 32.2. Test read concern/write concern

Thay write concern từ policy yếu sang majority có thể tăng latency nhưng mang lại durability/ACK guarantee cần cho nghiệp vụ. Không tối ưu p99 bằng cách hạ consistency nếu làm mất yêu cầu correctness.

### 32.3. Một kịch bản benchmark

```text
A: Point lookup by tenant+orderId
B: Range scan by tenant+createdAt
C: Aggregation by day
D: Multi-document transaction
```

Đo p50/p95/p99, QPS, docs examined, index usage và cache states **riêng** cho A/B/C/D.

## 33. Cassandra: partition size, coordinator và compaction tail

Một query CQL có thể rất nhanh khi partition nhỏ, nhưng p99 tăng khi:

- Một số partition rất rộng/hot.
- Tombstones làm tăng khối lượng đọc.
- Compaction/SSTable read amplification.
- Coordinator/node bị GC pause.
- Read repair/replica coordination theo semantics.
- Consistency level tăng số replica cần phản hồi.
- Network cross-DC routing.
- Prepared query routing không targeted.
- Paging over large partitions.

### 33.1. Vì sao cùng query shape nhưng khác latency?

```sql
SELECT *
FROM events_by_user
WHERE user_id = ?
LIMIT 100;
```

Một user có 100 events; user khác có hàng triệu events và tombstones. Dù query text như nhau, data distribution và partition layout khác.

Cần benchmark **hot/cold/large partitions** thay vì dùng toàn keys đồng đều.

### 33.2. Đo coordinator vs client

Cassandra Java Driver metrics có thể ghi request latency và per-node information tùy version; server-side latency, compaction, GC, tombstones giúp tìm nguyên nhân. Đừng đặt tên một client timer là server CPU time.

## 34. DynamoDB: mean tốt vẫn có GSI/hot-key throttling

DynamoDB thường có point reads/writes với mô hình partition key. Những nguồn p99 cao có thể gồm:

- Hot partition key.
- GSI write/read throttling.
- Capacity/traffic burst.
- Retry sau throttling.
- Network/region mismatch.
- FilterExpression làm đọc nhiều dữ liệu hơn output.
- Scan thay vì Query targeted.
- Nhiều trang `LastEvaluatedKey`.
- Large item payload.
- Conditional conflicts hoặc transaction overhead.

### 34.1. Một call thành công có thể chứa nhiều attempts

AWS SDK có retry behavior tùy operation/config. Nếu DynamoDB trả throttle hai lần rồi lần thứ ba thành công:

```text
Logical client call count = 1
HTTP attempts = 3
User-visible latency = tổng attempts + backoff
```

Chỉ đo thời gian thành công của lần cuối sẽ đánh giá thấp latency client.

### 34.2. Tách latency và capacity units

Một Query trả ít items nhưng tiêu thụ nhiều RCUs do filter sau read hoặc access pattern không tối ưu; p99 có thể bình thường ở tải thấp nhưng tăng mạnh khi capacity bão hòa.

### 34.3. GSI consistency

Không so strongly consistent base-table read với eventually consistent GSI read như cùng một thao tác nếu business yêu cầu tính mới. Latency nhanh nhưng dữ liệu stale không đạt correctness SLO.

## 35. Redis cache làm thay đổi phân bố p99

Giả sử:

```text
Redis HIT:  2 ms
DB MISS: 200 ms
Hit ratio: 95%
```

Nếu 95% requests là HIT và 5% MISS, p50 thường gần 2 ms, còn p99 có thể nằm trong nhóm MISS.

**Mean có thể thấp** nhưng phần đuôi phản ánh đường MISS.

### 35.1. TTL đồng bộ làm tail nhảy theo thời gian

Khi hàng nghìn keys expire cùng lúc, MISS QPS tăng, source bị quá tải và p99 có thể tăng từ 100 ms lên nhiều giây trong một khoảng ngắn.

### 35.2. Chỉ dùng p99 để tối ưu cache là chưa đủ

Cần đo:

```text
cacheHitRatio
cacheMissRate
cacheStaleServedRate
sourceReadQPS
singleFlightCoalescedCalls
sourceConcurrency
cacheConnectionErrorRate
```

Một cache phục vụ giá cũ rất nhanh vẫn không đạt business correctness.

### 35.3. Phân đoạn HIT/MISS

Báo cáo:

| Loại | p50 | p95 | p99 |
| --- | ---: | ---: | ---: |
| Cache HIT | ... | ... | ... |
| Cache MISS | ... | ... | ... |
| Cache ERROR fallback | ... | ... | ... |

Cùng với **tỷ trọng traffic** từng loại, vì tổng thể thay đổi nếu mix thay đổi.

## 36. Elasticsearch/OpenSearch: tail do scatter–gather

Một search request có thể gửi tới nhiều shards. Thời gian end-to-end thường bị ảnh hưởng bởi những shard chậm và coordination overhead.

```text
Coordinator
  |- shard A: 10 ms
  |- shard B: 12 ms
  |- shard C: 15 ms
  |- shard D: 400 ms
Response sau khi đủ kết quả theo query contract
```

Dù đa số shards rất nhanh, một slow shard có thể làm request chậm.

### 36.1. Không nhầm HTTP success với nội dung đúng

Một search API có thể trả partial results hoặc shard failures theo cơ chế/version/config phù hợp. Benchmark phải kiểm tra response body, errors, total hits/consistency và số shards thành công.

### 36.2. Đo query shape và index state

Các yếu tố:

- Query DSL và filter selectivity.
- Aggregation cardinality.
- Sort/search_after/PIT behavior.
- Refresh/merge/segment changes.
- JVM heap và GC.
- Shard sizing, routing và replication.
- Bulk indexing đồng thời.

### 36.3. Profile có overhead

Dùng profile API và slow logs để điều tra có mục tiêu; bật mọi request trong test quá tải có thể làm kết quả benchmark bị ảnh hưởng.

## 37. Fan-out: p99 hệ thống không đồng nhất với p99 một dependency

Một API cần gọi 10 downstream services song song và chờ tất cả:

```text
API
 |- DB read 1
 |- DB read 2
 |- ...
 |- DB read 10
```

Nếu mỗi call độc lập có xác suất 99% hoàn tất trước 100 ms:

\[
P(\text{cả 10 calls}\le100ms)=0,99^{10}\approx0,904
\]

Theo mô hình độc lập, chỉ khoảng **90,4%** API requests có toàn bộ calls dưới ngưỡng 100 ms.

### 37.1. Đây là minh họa có giả định

- Các calls phải độc lập.
- Mỗi call có cùng phân bố.
- API chờ đủ tất cả.
- Chưa tính overhead khác.

Trong thực tế, calls có thể tương quan do cùng network/database cluster. Khi tương quan, phép nhân trên không áp dụng trực tiếp.

### 37.2. Hướng giảm tail

- Giảm fan-out không cần thiết.
- Tạo targeted query/read model.
- Dùng bounded parallelism.
- Cache dữ liệu thích hợp.
- Deadline và partial-result policy khi business cho phép.
- Hedged requests chỉ trong điều kiện an toàn và có budget.
- Loại bỏ các calls không nằm trên critical path.

Một p99 thấp ở mỗi query **không tự bảo đảm p99 thấp cho API fan-out**.

## 38. Retries có thể làm p99 xấu hoặc “đẹp giả”

Giả sử:

```text
Attempt 1: 500 ms -> timeout
Backoff:   100 ms
Attempt 2:  30 ms -> success

User-visible latency khoảng 630 ms
```

Nếu dashboard chỉ ghi `attempt 2 = 30 ms`, p99 sẽ rất đẹp nhưng người dùng đã chờ hơn nửa giây.

### 38.1. Đo cả hai scope

```text
DB attempt duration histogram
Logical DB call duration histogram (bao retry/backoff)
HTTP end-to-end duration histogram
Retry attempts per logical operation
```

Không cộng các histograms này như cùng population.

### 38.2. Retry amplification

Khi cache down, gateway retry 2 lần, app retry 3 lần, driver retry 2 lần, một intent có thể tạo rất nhiều attempts tùy cách các tầng phối hợp.

Chỉ tăng retries để “giảm error rate” có thể làm p99 và backend load tệ hơn.

### 38.3. Timeout sau write có kết quả không chắc chắn

Một `UpdateItem` hay MongoDB write có thể commit trước khi ACK mất. Retry dùng ID mới có thể tạo duplicate business effect. Latency dashboard không thay thế idempotency và authoritative outcome lookup.

## 39. Percentile của read khác write

Đừng báo một dòng chung “NoSQL p99” khi workload có nhiều loại:

| Operation | Đặc điểm |
| --- | --- |
| GET point lookup | Chủ yếu tìm theo key, thường nhạy cache |
| Range query | Phụ thuộc partition/index và kích thước kết quả |
| Aggregation | CPU/memory/shard fan-out |
| Insert/Put | Serialization, durability, replication |
| Conditional update | Conflict và retries |
| Multi-document transaction | Coordination, commit |
| Bulk write | Batch size và partial failures |
| Delete/TTL cleanup | Tombstone, background work |
| CDC projection | Event lag và processing time |

### 39.1. Write concern là yếu tố quan trọng

Ví dụ MongoDB write `w:1` và `majority` không có cùng ACK/durability contract. Nếu p99 của majority write cao hơn, không có nghĩa chỉ số thấp hơn luôn là lựa chọn tốt; cần giữ yêu cầu nghiệp vụ.

### 39.2. Độ trễ replica và freshness là chỉ số khác

Read từ một replica nhanh nhưng stale hơn dữ liệu authoritative có thể vi phạm yêu cầu read-your-writes. SLO có thể cần cả:

```text
p99 read latency <= threshold
freshness/consistency violation <= threshold
```

## 40. Thay đổi batch size có thể làm mean và p99 khác hướng

Trong bulk load, tăng batch size có thể:

- Giảm số network round trips.
- Cải thiện throughput trung bình.
- Tăng latency của từng batch lớn.
- Tăng tail do retries/partial failures.
- Tăng memory và GC.

### 40.1. Phải nêu đơn vị đo

```text
Latency per batch
Latency per item
Time to acknowledge last item
End-to-end pipeline completion time
```

Một batch 1.000 items trong 500 ms tương ứng 2.000 items/s nếu xử lý tuần tự một batch; không có nghĩa **mọi item** trải nghiệm latency 0,5 ms.

### 40.2. Báo cáo hai cấp

Đo throughput items/s và batch duration histogram; nếu user chờ từng item, đo cả item end-to-end latency.

## 41. Phương pháp đo tải tái lập

Một kế hoạch benchmark NoSQL nên xác định:

1. **Mục tiêu:** SLO latency, throughput và correctness.
2. **Operation mix:** GET, Query, Update, Scan, Transaction.
3. **Dataset:** số rows/documents, kích thước, phân bố key, index.
4. **Workload arrival:** open-loop/closed-loop, rate, burst, think time.
5. **Concurrency:** clients, threads, max in-flight.
6. **Topology:** shards/replicas/regions, quorum/read preferences.
7. **Runtime:** Java version, driver, connection pool, GC.
8. **Cache:** warm/cold, HIT ratio, TTL, eviction.
9. **Background load:** compaction, CDC, backup, reindex, bulk ingestion.
10. **Duration:** warmup, steady state, fault phase, recovery.
11. **Measurement:** timer scope, buckets, sampling, outcomes.
12. **Acceptance:** p50/p95/p99, error rate, freshness, resource budgets.
13. **Repetition:** chạy nhiều lượt và báo variability.
14. **Evidence:** logs/traces, config, dataset seed và metrics source.

### 41.1. Không bỏ qua correctness

Tăng QPS bằng cách:

- Bỏ conditional check.
- Giảm read consistency.
- Tắt durability.
- Bỏ validation.
- Không chờ write ACK cần thiết.

có thể cho latency đẹp nhưng làm hệ sai nghiệp vụ. Giữ cùng correctness contract khi so hiệu năng.

## 42. Benchmark baseline và so sánh sau tối ưu

Ví dụ báo cáo có cấu trúc:

| Chỉ số | Trước | Sau | Cần giải thích |
| --- | ---: | ---: | --- |
| RPS thực hoàn tất | 2.000 | 2.000 | Cùng offered load? |
| p50 | 12 ms | 11 ms | Trung tâm |
| p95 | 110 ms | 70 ms | Đuôi 5% |
| p99 | 800 ms | 250 ms | Đuôi 1% |
| Mean | 45 ms | 32 ms | Tổng thời gian |
| Error rate | 0,5% | 0,4% | Có loại timeout ra không? |
| Source QPS | 3.000 | 2.100 | Query/cache behavior |
| CPU max shard | 95% | 73% | Hotspot |
| Cache HIT | 80% | 88% | Mix đã thay đổi? |

Số liệu chỉ **minh họa**; không phải kết quả benchmark đã chạy.

### 42.1. Thông tin phải đi kèm

```text
Same dataset and key distribution?
Same read/write concern?
Same cache warm state?
Same request arrival and error inclusion?
Same Java/driver/server version?
Same duration and histogram boundaries?
```

Nếu không, “p99 giảm 69%” có thể do workload nhẹ hơn, nhiều cache HIT hơn hoặc bỏ requests timeout.

## 43. Load ladder: tìm điểm gãy của tail

Thay vì thử một RPS duy nhất, tăng tải theo bậc:

```text
500 -> 1000 -> 1500 -> 2000 -> 2500 -> 3000 RPS
```

Tại mỗi bậc, giữ đủ lâu để ổn định và ghi:

```text
Achieved throughput
p50/p95/p99
Error/timeout rate
Queue depth
Pool wait
CPU/IO/throttling
Correctness
```

### 43.1. Knee point

Có thể xuất hiện vùng:

```text
RPS     p50     p95     p99
1000     8ms    20ms    40ms
1500     9ms    30ms    70ms
2000    10ms    50ms   200ms
2500    12ms   200ms  1800ms
```

Đây là ví dụ hình dạng **latency knee**: p99 tăng vọt khi gần ngưỡng bão hòa.

### 43.2. Không lấy RPS cao nhất làm công suất an toàn

Nếu 2.500 RPS tạo p99=1,8 s và 5% timeout, công suất phục vụ theo SLO có thể thấp hơn nhiều. Nên chọn headroom cho bursts, failover, backup và tái cân bằng.

### 43.3. Chú ý phục hồi

Một hệ có thể xử lý 2.500 RPS trong vài phút nhưng queue tiếp tục tăng, khiến sau khi dừng load vẫn cần lâu mới trả hết backlog. Benchmark phải quan sát steady state và recovery.

## 44. Burst test: p99 có thể xấu dù mean lưu lượng thấp

Một workload:

```text
0-50s:  500 RPS
50-55s: 10.000 RPS
55-60s: 500 RPS
```

Mean trong 60 giây có thể trông vừa phải, nhưng burst 5 giây làm connection pool và DB queue bão hòa.

### 44.1. Đo theo cửa sổ ngắn

- p99 1s/5s quanh burst, khi sample đủ.
- Requests scheduled vs sent.
- Max queue depth.
- Source throttling.
- Recovery time.
- Tail latency của requests bắt đầu ngay sau burst.

### 44.2. Không chỉ dùng mean RPS theo phút

Một trung bình 1.300 RPS có thể che đỉnh 10.000 RPS. Capacity cần dựa trên **arrival peak và queueing behavior** khi peak có ý nghĩa với business.

## 45. Hot partition test: phân bố key quan trọng hơn số document

Hai datasets cùng 10 triệu records:

**Dataset A:** partition keys phân bố đều.

**Dataset B:** 60% requests chạm một partition key hoặc một nhóm nhỏ keys.

Mean request latency ở tải thấp có thể tương tự, nhưng khi tăng tải, Dataset B gây hot partition và p99 bùng lên.

### 45.1. Test phải có skew

Có thể mô phỏng:

```text
Uniform keys
Zipf-like popularity
Single hot key
Large partition
Cross-tenant skew
```

### 45.2. Đo per partition/node

Dashboard trung bình cluster có thể cho CPU 50% dù một shard ở 99%. Cần max/percentile per node, queue/IO và top-contributor diagnostics có kiểm soát.

### 45.3. Tránh làm nổ metric labels

Không gắn raw tenant/key IDs vào mọi histogram. Dùng bounded diagnostic Top-N hoặc sampled trace có bảo mật để phân tích hotspot.

## 46. GC, compaction, checkpoint và tail latency

NoSQL có background work ảnh hưởng latency:

- LSM compaction.
- WAL/journal flush.
- Checkpoint.
- Garbage collection.
- Index merge.
- Replica catch-up.
- Snapshot/backup.
- Balancing/migration.
- TTL/tombstone cleanup.

Các tác vụ này có thể chỉ làm chậm một tỷ lệ nhỏ requests nhưng kéo p99 lên mạnh.

### 46.1. Tương quan theo thời gian

Khi p99 tăng:

```text
p99 spike 10:05:00
compaction backlog spike 10:05:00
disk write latency spike 10:05:00
```

Đó là dấu hiệu cần điều tra, **chưa là bằng chứng nhân quả tuyệt đối**. Cần thêm query plan, node scope và experiments có kiểm soát.

### 46.2. Đừng chỉ benchmark sau khi compaction xong

Nếu production liên tục ghi dữ liệu và compaction xảy ra thường xuyên, một benchmark chỉ chạy khi hệ hoàn toàn idle sẽ quá lạc quan.

## 47. Khi có replication và quorum

Trong một operation cần phản hồi từ nhiều replicas, tail latency có thể chịu ảnh hưởng bởi:

- Replica chậm.
- Network RTT liên vùng.
- Coordinator/leader congestion.
- Failover/re-election.
- Consistency level.
- Retry/speculative execution.
- Read repair hoặc sync background.

### 47.1. Không đánh đổi correctness để đạt p99

Một write chỉ ACK local có thể nhanh hơn write cần multiple replicas, nhưng bảo đảm durability khác nhau. Nếu nghiệp vụ yêu cầu mức bền cao, benchmark phải giữ cùng guarantee.

### 47.2. Thử failure mode

Đo p99:

```text
Healthy cluster
One replica slow
One replica unavailable
Leader failover
Cross-region latency increase
```

Đồng thời đo error rate và unknown outcomes. Một percentile chỉ của successful requests có thể trông tốt khi nhiều requests đã thất bại.

## 48. Đo freshness tách biệt với latency

Một API đọc từ cache/replica có thể trả trong 5 ms, nhưng dữ liệu đã cũ 30 giây.

Nếu yêu cầu là “sau khi cập nhật, người dùng phải nhìn thấy dữ liệu mới trong 2 giây”, latency p99 tốt **không đủ**.

Các metric khác:

```text
source-to-projection lag
stale read ratio
max observed version lag
time to converge after write
read-your-writes violations
delete propagation lag
```

### 48.1. Không trộn freshness p99 với request p99

`request duration p99` và `replication lag p99` đo hai phân bố khác nhau, có populations và timestamps khác nhau. Nên báo riêng và giải thích tính chính xác clock/source version.

### 48.2. Dữ liệu tiền và quyền

Một cách tối ưu query dùng eventual replica để giảm p99 có thể làm sai quyết định thanh toán hoặc thu hồi quyền. SLO cần xét invariant trước khi xét tốc độ.

## 49. SLO: chuyển biểu đồ thành cam kết có thể kiểm chứng

Ví dụ:

> Trong 30 ngày, ít nhất 99% yêu cầu `GET /orders/{id}` được phục vụ trong 200 ms và không trả lỗi thuộc diện tính vào SLO.

Cần định nghĩa:

- In-scope endpoints.
- Quan sát ở client/gateway/application.
- Những request nào được tính.
- “Good”/“bad” event.
- Error handling.
- Time window.
- Sampling/data completeness.
- Mức freshness/consistency đi kèm nếu business cần.

### 49.1. p99 và tỷ lệ good events liên quan nhưng khác cách vận hành

Nếu SLO là `duration <=200ms` cho 99% requests, đo trực tiếp good-event ratio có thể thuận tiện hơn p99 được nội suy từ histogram.

p99 dashboard giúp xem trend, nhưng **đếm violations** giúp tính error budget.

### 49.2. Error budget burn rate

Khi tỷ lệ bad events tăng nhanh, error budget có thể bị tiêu nhanh hơn tốc độ cho phép. Alerts theo burn rate trên các khoảng ngắn/dài thường mang tính hành động hơn việc báo động mỗi lần p99 nhích vài ms.

### 49.3. Không hứa p99 tuyệt đối mỗi giây

Với traffic thấp, p99 từng giây có thể chỉ là một observation. SLO cần cửa sổ đánh giá và quy tắc số liệu rõ.

## 50. Ngưỡng cảnh báo không chỉ dựa vào một p99

Một alert:

```text
p99 > 500 ms
```

có thể gây nhiễu nếu traffic chỉ có 15 requests/phút, hoặc bỏ sót khi 30% requests timeout và timer chỉ ghi success.

Cân nhắc kết hợp:

```text
Minimum sample count
Good/bad event ratio
Error rate
p99/p95 trend
Pool wait/queue depth
Source saturation
Unknown outcomes
```

### 50.1. Ví dụ pseudo-alert

```text
IF requests_in_5m >= minimum_sample_count
AND (latency_bad_ratio > SLO_budget_rate
     OR timeout_rate > limit)
FOR defined_duration
THEN alert on-call
```

Threshold cụ thể phải do service SLO/capacity quyết định.

### 50.2. Cảnh báo theo quyền/tiền có mức ưu tiên khác

Một lỗi thanh toán hoặc phân quyền có thể nghiêm trọng dù tần suất thấp và p99 không thay đổi. Không chỉ dùng latency alert để giám sát correctness.

## 51. Đọc bảng kết quả benchmark một cách có kỷ luật

Khi nhận báo cáo “p99 trước 800 ms, sau 250 ms”, hỏi:

1. Cùng **scope** end-to-end hay driver/server?
2. Cùng **workload mix**?
3. Cùng **RPS thực** hay chỉ offered target?
4. Cùng **dataset size và key distribution**?
5. Cùng **cache warm state**?
6. Cùng **consistency/write concern**?
7. Cùng **number of successes/timeouts**?
8. Cùng **measurement window**?
9. Cùng **quantile method/histogram buckets**?
10. Cùng **driver/server/runtime versions**?
11. Có thay đổi retries/admission control không?
12. Có enough samples và nhiều lần lặp không?
13. Mức **resource saturation** thay đổi thế nào?
14. Correctness và freshness có được giữ không?
15. Có source logs/traces giải thích thay đổi không?

Nếu một câu trả lời chưa rõ, báo cáo p99 vẫn có thể hữu ích như tín hiệu nhưng **chưa đủ làm bằng chứng nguyên nhân**.

## 52. Runbook: p99 tăng nhưng p50 không đổi

**Triệu chứng:** `p50=12ms` ổn định, `p99` tăng từ 100 ms lên 2 s.

1. Kiểm tra số mẫu và histogram method; loại trừ artifact/aggregation.
2. Xem error/timeout rate, có loại errors khỏi latency không.
3. So p95/p99 theo operation/query fingerprint.
4. Phân đoạn HIT/MISS, region, instance, shard.
5. Xem connection pool wait/queue depth.
6. Xem retry attempts/backoff và server selection.
7. Xem compaction/GC/IO/replication events.
8. Tìm hot key hoặc partition lớn.
9. Xem deployment, index/schema hoặc routing changes.
10. Lấy slow traces và query plans.
11. Thử mitigation có kiểm soát: rate limit, index fix, pool leak fix, rollback, capacity.
12. Xác minh p99 **và** success/correctness sau thay đổi.

### 52.1. Đừng chỉ tăng timeout

Tăng API timeout từ 2 giây lên 30 giây có thể giảm số request báo timeout nhưng tăng queueing, giữ connections lâu và làm người dùng chờ lâu hơn. Phải tìm bottleneck và quy tắc retry/admission trước.

## 53. Runbook: mean giảm nhưng p99 tăng

**Triệu chứng:** mean từ 70 ms xuống 30 ms, p99 từ 300 ms lên 1.500 ms.

1. Kiểm tra workload mix: cache HIT tăng?
2. Kiểm tra tỷ lệ slow path: scan, GSI, transaction, MISS.
3. Kiểm tra các request cực chậm: timeout, failover, GC, compaction.
4. Xem bursts và coordinated omission.
5. Phân tách outcome classes và retry.
6. So traffic per tenant tier/region/shard.
7. Xác định tail có ảnh hưởng đúng user segment quan trọng không.
8. Chọn phương án giảm tail mà không hạ consistency sai.

Có thể hệ đã cải thiện rất nhiều reads bình thường nhưng làm một đường write hiếm chậm hơn; mean gộp không thể thay việc xem riêng đường đó.

## 54. Runbook: p99 đẹp nhưng error rate tăng

**Triệu chứng:** p99 successful reads giảm từ 300 ms xuống 100 ms, HTTP 5xx tăng từ 0,1% lên 8%.

1. Kiểm tra timer có ghi failed requests không.
2. Xem gateway timeout/rejection/circuit-open metrics.
3. Xem retry budget và max in-flight.
4. Kiểm tra requests bị dropped trước khi vào application.
5. Đối chiếu offered rate với completed throughput.
6. Đánh giá overload protection có từ chối quá nhiều requests không.
7. Báo cáo p99 cùng success rate và good-event SLO.
8. Thử thay đổi dưới cùng load, cùng admission policy.

Không gọi hệ đã nhanh hơn chỉ vì nó từ chối requests chậm hơn.

## 55. Anti-patterns về phân vị và đo tải

| Ngộ nhận / anti-pattern | Vì sao sai | Cách tốt hơn |
| --- | --- | --- |
| “Mean thấp nên mọi người đều nhanh” | Outlier/tail bị che | Xem p95/p99/threshold |
| “p99 là request chậm nhất” | 1% còn lại có thể rất chậm | Xem max/p99.9/count |
| “p99=100ms nghĩa 99% request tương lai chắc chắn dưới 100ms” | Mẫu và phân bố có thể đổi | Nêu window và uncertainty |
| “Một tool tính p95 khác là bug” | Quantile algorithm khác | Công bố nearest-rank/interpolation |
| “p99 20 mẫu có độ tin cậy cao” | Tail gần như không có mẫu | Nêu n, khoảng rộng/lặp lại |
| “Bỏ timeout khỏi Timer cho sạch” | Làm p99 đẹp giả | Đo terminal outcomes |
| “Timeout=server chưa ghi” | Commit có thể thành công | Unknown outcome và idempotency |
| “Cộng p99 của các spans” | Quantile không tuyến tính | Đo end-to-end |
| “Average p99 across nodes” | Không tái tạo phân bố chung | Merge histograms/sketches |
| “Weighted average p99 là global p99” | Vẫn sai | Merge distributions |
| “Chỉ nhìn cluster average CPU” | Che hot shard | Per-node/max/queue metrics |
| “p50 ổn nghĩa không có vấn đề” | Tail có thể tăng vọt | p95/p99 và errors |
| “Tăng cache HIT luôn tốt” | Stale/incorrect data | Freshness SLO |
| “Test 10.000 unique keys bao phủ hot key” | Distribution khác | Skewed/hot-key tests |
| “Closed-loop luôn mô phỏng mọi traffic” | Có thể coordinated omission | Chọn workload model |
| “Tăng RPS target nghĩa generator đã gửi đủ” | Generator có thể nghẽn | Offered/sent/completed |
| “Một lượt benchmark là đủ” | Nhiễu GC/compaction | Repeated runs và metadata |
| “Warm cache benchmark đại diện cold start” | State khác | Đo riêng cold/warm |
| “Client latency bằng server execution” | Pool/network/retry | Phân rã các tầng |
| “GSI read nhanh là đủ” | Có thể stale | Consistency/freshness |
| “Giảm write concern để cải thiện p99” | Mất durability invariant | Giữ correctness contract |
| “Bật tracing mọi request không có cost” | Overhead/PII | Sampling và kiểm soát |
| “p99 histogram là exact tới nanosecond” | Bucket/sketch approximation | Nêu sai số |
| “SLO chỉ cần p99” | Availability/correctness cũng quan trọng | Good-event ratio và invariants |
| “Thấy p99 tăng thì tăng pool” | Có thể tăng backend overload | Đo pool wait/server cap |
| “Thấy p99 tăng thì thêm retries” | Retry storm | Bounded retry/admission |
| “p99 thấp mà error rate cao vẫn thắng” | Sample-selection bias | Composite SLO |
| “Hedged request miễn phí” | Nhân tải nguồn | Budget và policy |
| “Log raw IDs vào histogram label” | Cardinality/PII | Bounded labels |
| “Timestamp lớn hơn nghĩa request commit sau” | Clock skew | Revision/log order |

## 56. Bài tập thực hành

### Bài 1 — Mean

Dữ liệu: `10, 10, 10, 10, 60` ms.

**Hỏi:** Mean là bao nhiêu?

**Gợi ý:** Tổng 100, chia 5 → 20 ms.

### Bài 2 — Median

Cùng dãy trên.

**Hỏi:** p50 theo nearest-rank?

**Gợi ý:** Phần tử thứ 3 → 10 ms.

### Bài 3 — p95 mẫu nhỏ

Dữ liệu: `10, 10, 10, 10, 60` ms.

**Hỏi:** p95 theo nearest-rank?

**Gợi ý:** `ceil(0,95*5)=5` → 60 ms.

### Bài 4 — 100 requests

95 requests 10 ms, 4 requests 100 ms, 1 request 5000 ms.

**Hỏi:** Mean, p95, p99, maximum?

**Gợi ý:** 63,5 ms; 10 ms; 100 ms; 5000 ms.

### Bài 5 — p99 không phải max

99 requests 20 ms, 1 request 2000 ms.

**Hỏi:** p99 nearest-rank là bao nhiêu?

**Gợi ý:** Thứ 99 là 20 ms; max 2000 ms.

### Bài 6 — Nội suy

Một thư viện báo p95 khác nearest-rank trên 10 samples.

**Hỏi:** Có được kết luận thư viện sai không?

**Gợi ý:** Chưa. Kiểm tra quantile definition/interpolation.

### Bài 7 — Sample count

Một endpoint chỉ có 30 requests/phút.

**Hỏi:** Vì sao p99 từng phút có thể dao động mạnh?

**Gợi ý:** Quá ít samples để ước lượng tail ổn định; báo n, count vượt ngưỡng.

### Bài 8 — Success-only metric

90 requests thành công nhanh, 10 requests timeout.

**Hỏi:** Tại sao p99 của chỉ 90 successes gây hiểu lầm?

**Gợi ý:** Loại bỏ 10% user experiences tệ nhất.

### Bài 9 — Unknown write

Một UpdateItem timeout sau khi server commit.

**Hỏi:** Có được log nó thành thất bại chắc chắn không?

**Gợi ý:** Không; outcome unknown, dùng operation ID/lookup.

### Bài 10 — Gộp p99

Node A 100 requests p99=500 ms, Node B 100.000 requests p99=20 ms.

**Hỏi:** Average p99=260 ms có là global p99 không?

**Gợi ý:** Không; quantile không tuyến tính.

### Bài 11 — Weighted p99

Team thử weighted mean theo request count của p99 từng node.

**Hỏi:** Đã đúng chưa?

**Gợi ý:** Chưa; cần merge histogram/raw distributions.

### Bài 12 — Histogram

Một classic histogram có bucket `le=0.2` chứa 990/1000 requests.

**Hỏi:** Ngưỡng 200ms đạt SLO 99% không, nếu các samples/outcomes đúng scope?

**Gợi ý:** Theo số đếm ngưỡng, đạt đúng 99%.

### Bài 13 — Buckets

SLO 200 ms nhưng buckets chỉ có 100 ms và 1.000 ms.

**Hỏi:** Có chính xác p99 quanh 200 ms không?

**Gợi ý:** Không; cần bucket gần SLO hơn.

### Bài 14 — PromQL `le`

Vì sao `sum by (le, operation)` có `le`?

**Gợi ý:** Classic histogram cần ranh giới buckets để tính quantile.

### Bài 15 — Latency tầng

Pool wait=700ms, DB server=20ms, serialization=10ms.

**Hỏi:** Chỉ số client gần 730ms có chứng minh server chậm không?

**Gợi ý:** Không; pool wait là phần lớn.

### Bài 16 — Fan-out

Một API chờ 10 independent services, mỗi service đáp ứng 100ms với xác suất 0,99.

**Hỏi:** Xác suất cả 10 nhanh là bao nhiêu?

**Gợi ý:** \(0,99^{10}\approx0,904\).

### Bài 17 — Coordinated omission

Load client chỉ gửi request mới sau khi request trước xong; server pause 3 giây.

**Hỏi:** Vì sao p99 có thể bị đánh giá thấp?

**Gợi ý:** Các arrivals đáng lẽ đến trong pause bị bỏ sót trong mô hình closed-loop.

### Bài 18 — Offered load

Target 5.000 RPS, generator chỉ gửi 3.000 RPS.

**Hỏi:** Có được kết luận server chịu được 5.000 RPS không?

**Gợi ý:** Không; cần đo actual sent/completed.

### Bài 19 — Cold cache

Baseline warm HIT 99%, lần sau chạy cold HIT 5%.

**Hỏi:** Có nên so p99 trực tiếp như thay đổi driver?

**Gợi ý:** Không; cache state là biến gây nhiễu.

### Bài 20 — Hot partition

Cluster CPU average 50%, một shard CPU 100%.

**Hỏi:** Vì sao p99 có thể tăng?

**Gợi ý:** Requests tới shard nóng xếp hàng dù cluster average còn dư.

### Bài 21 — Cassandra

Hai users có partition sizes rất khác; cùng query `LIMIT 100`.

**Hỏi:** Có thể có tail khác nhau không?

**Gợi ý:** Có; tombstones/SSTables/partition layout gây khác cost.

### Bài 22 — DynamoDB

Một GetItem bị throttled rồi SDK retry hai lần.

**Hỏi:** Đo attempt cuối có đủ user-visible latency không?

**Gợi ý:** Không; cần tổng attempts/backoff.

### Bài 23 — Redis

HIT ratio 95%, MISS latency 200ms, HIT 2ms.

**Hỏi:** Vì sao p99 có thể nằm trong nhóm MISS?

**Gợi ý:** MISS chiếm 5%, vượt vùng 99th percentile của phân bố gộp.

### Bài 24 — Search

Search fan-out tới 8 shards, một shard mất 400ms.

**Hỏi:** Coordinator end-to-end có thể bị ảnh hưởng không?

**Gợi ý:** Có, nếu request phải chờ shard đó.

### Bài 25 — Write concern

Một benchmark giảm consistency/durability để p99 đẹp hơn.

**Hỏi:** Đã là tối ưu cùng yêu cầu chưa?

**Gợi ý:** Không nếu correctness contract thay đổi.

### Bài 26 — p50 ổn, p99 tăng

p50=10ms giữ nguyên, p99=100ms→1s.

**Hỏi:** Ba nguyên nhân nên điều tra?

**Gợi ý:** Retry/failover, hot shard, pool wait, compaction/GC, query mix.

### Bài 27 — p99 đẹp, lỗi tăng

p99 successes giảm từ 300 xuống 80ms, error rate tăng từ 1% lên 20%.

**Hỏi:** Hệ có chắc tốt hơn?

**Gợi ý:** Không; cần user-visible good-event SLO.

### Bài 28 — Window

Incident kéo dài 1 phút trong 1 giờ.

**Hỏi:** Vì sao p99 theo giờ có thể che spike?

**Gợi ý:** Dữ liệu gộp pha loãng phân bố tùy traffic mix; xem cửa sổ ngắn và bad event rate.

### Bài 29 — Metric cardinality

Team gắn `orderId` vào mỗi Timer.

**Hỏi:** Rủi ro gì?

**Gợi ý:** Nổ time series; dùng operation/query fingerprint bounded, IDs trong traces/logs có bảo mật.

### Bài 30 — Thiết kế benchmark end-to-end

Một Java Order API dùng MongoDB (nguồn), Redis cache và Elasticsearch (read model). Bắt đầu 2.000 RPS, 80% reads, 20% writes, đồng thời có flash sale hot product.

**Yêu cầu:** Thiết kế workload, distributions, warm/cold phases, histogram buckets, metrics, error treatment, coordinated-omission policy, index/consistency controls, load ladder, failover test, SLO và báo cáo p50/p95/p99.

**Gợi ý:** Tách HTTP/source/cache/search populations; giữ stable correctness policy; dùng open-loop khi arrivals độc lập; đo offered/sent/completed, timeouts, source QPS, pool wait, hot shard, freshness, retries và histogram buckets quanh SLO. Lặp lại benchmark, kiểm tra version/driver/data state và công bố scope.

## 57. Checklist trước khi tin một con số p99

- **Một observation bắt đầu và kết thúc khi nào?**
- **Đang đo client, driver, server hay end-to-end API?**
- **Population gồm successes, timeouts, errors và cancellations ra sao?**
- **Có phân biệt logical operation và retry attempts?**
- **p99 được tính bằng nearest-rank, nội suy, histogram hay sketch?**
- **Histogram buckets có phù hợp SLO threshold?**
- **Số mẫu và thời gian đo có đủ để kết luận?**
- **Có sampling hoặc coordinated omission không?**
- **Actual sent/completed RPS có bằng offered workload không?**
- **Window 1 phút/5 phút/1 giờ được ghi rõ?**
- **Có làm sai bằng cách trung bình p99 từ nhiều nodes?**
- **Có so cùng dataset, query shape và key distribution?**
- **Cache state warm/cold/HIT/MISS có tương đương?**
- **Write concern/read concern/consistency có được giữ?**
- **GC, compaction, backup và failover có được tính?**
- **Pool wait/queue depth/server execution có metrics riêng?**
- **Có per-shard/hot partition analysis không?**
- **p50/p95/p99 có đi kèm error/timeout rate?**
- **Có threshold exceedance/good-event ratio theo SLO?**
- **Freshness/correctness có được đo riêng?**
- **Có lặp lại test và ghi run metadata?**
- **Các metric labels có cardinality hữu hạn và không rò PII?**

## 58. Kết luận

**Trung bình cộng chỉ cho biết tổng thời gian chia số mẫu; nó không nói người dùng ở phần đuôi phải chờ bao lâu.** p50 phản ánh trải nghiệm điển hình, p95 và p99 giúp nhìn thấy nhóm requests chậm hơn, nhưng chính những phân vị này cũng có giới hạn: phụ thuộc số mẫu, cửa sổ đo, thuật toán ước lượng, cách chọn population và những lỗi bị bỏ qua.

Trong NoSQL, tail latency có thể đến từ **hot partition, scatter–gather, cache MISS, connection pool wait, GC, compaction, quorum, throttling, failover và retry**. Muốn xác định nguyên nhân phải đo cả **user-visible duration**, driver/client duration, server diagnostics, source load và correctness, chứ không suy từ một con số p99.

Một báo cáo hiệu năng đáng tin phải **nói rõ p99 của ai, trong điều kiện nào, dựa trên bao nhiêu mẫu, tính theo thuật toán nào và có tính cả lỗi không**. Dùng histogram/sketch đúng cách, kiểm thử với workload thực, tránh coordinated omission, theo dõi error budget và giữ invariant nghiệp vụ. **Mục tiêu cuối cùng không phải làm đẹp giá trị trung bình hay p99, mà là phục vụ đa số người dùng nhanh, giảm phần đuôi tệ nhất và bảo đảm dữ liệu vẫn đúng khi hệ thống chịu tải.**
