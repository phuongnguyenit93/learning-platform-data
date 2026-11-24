# Năng lực phục vụ, độ trễ và ước lượng số lời gọi đồng thời

Khi triển khai Circuit Breaker trong Spring Cloud, cần biết dịch vụ phụ thuộc có thể xử lý bao nhiêu lời gọi, độ trễ thay đổi ra sao khi tải tăng và có bao nhiêu request đang chờ cùng lúc. Ba đại lượng này liên quan trực tiếp đến khả năng bảo vệ dịch vụ: thông lượng cho biết tốc độ xử lý, độ trễ cho biết thời gian hoàn tất, còn số lời gọi đồng thời cho biết lượng công việc đang chiếm tài nguyên tại một thời điểm.

Circuit Breaker giúp ngừng gửi lời gọi mới khi dependency có dấu hiệu lỗi hoặc chậm. Tuy nhiên, nó không tự giới hạn số lời gọi đồng thời khi đang CLOSED. Để ước lượng và kiểm soát tải, cần kết hợp số liệu thực tế, định luật Little, timeout, Bulkhead, giới hạn connection pool và kiểm thử tải. Ước lượng đúng giúp chọn giới hạn đồng thời có cơ sở, giảm nguy cơ cạn thread/connection và tránh tạo thêm hàng đợi khi dependency đã bão hòa.

## 1. Ba đại lượng cần đo

**Thông lượng (throughput)** là số lời gọi hoàn tất trong một đơn vị thời gian, thường đo bằng request/second (RPS) hoặc calls/second. Cần phân biệt thông lượng request vào API với thông lượng lời gọi đến một dependency. Một request có thể gọi Catalog hai lần, Inventory một lần và Payment một lần; vì vậy số lời gọi dependency có thể lớn hơn số request đầu vào.

**Độ trễ (latency)** là thời gian từ lúc bắt đầu một thao tác đến khi nhận được kết quả. Nên theo dõi nhiều percentile thay vì chỉ dùng trung bình:

- **p50:** một nửa số lời gọi hoàn tất trong thời gian này hoặc nhanh hơn.
- **p95:** 95% lời gọi hoàn tất trong thời gian này hoặc nhanh hơn.
- **p99:** 99% lời gọi hoàn tất trong thời gian này hoặc nhanh hơn.

p95 và p99 giúp phát hiện tail latency, tức nhóm request chậm kéo dài dù phần lớn request vẫn nhanh. Độ trễ trung bình hữu ích cho ước lượng số lời gọi đang chạy, nhưng percentile cao cần được theo dõi để đặt timeout và bảo đảm SLO.

**Số lời gọi đồng thời (in-flight concurrency)** là số lời gọi đã bắt đầu nhưng chưa hoàn tất tại cùng một thời điểm. Một dependency có thể xử lý 500 calls/second với độ trễ 100 ms và chỉ có khoảng 50 lời gọi đang chạy trung bình. Nếu độ trễ tăng lên một giây trong khi thông lượng vẫn giữ 500 calls/second, số lời gọi đang chạy trung bình tăng lên khoảng 500.

| Đại lượng | Đơn vị thường dùng | Câu hỏi trả lời |
|---|---|---|
| Throughput | requests/s hoặc calls/s | Hệ thống hoàn tất bao nhiêu lời gọi mỗi giây? |
| Latency | ms hoặc s | Một lời gọi mất bao lâu để hoàn tất? |
| In-flight concurrency | số lời gọi | Có bao nhiêu lời gọi đang chiếm tài nguyên cùng lúc? |
| Error rate | % | Bao nhiêu lời gọi kết thúc bằng lỗi? |
| Saturation | %, queue depth, pool usage | Tài nguyên đang gần giới hạn đến đâu? |

Đo đúng phạm vi rất quan trọng. Khi tính tải cho Catalog, hãy dùng số lời gọi đến Catalog, không lấy tổng RPS của API nếu mỗi request chỉ gọi Catalog trong một tỷ lệ nhất định.

## 2. Dùng định luật Little để ước lượng concurrency

Định luật Little mô tả mối quan hệ giữa số công việc trung bình trong một hệ thống ổn định, tốc độ công việc đi qua hệ thống và thời gian trung bình một công việc ở trong hệ thống:

\[
L = \lambda \times W
\]

Trong đó:

- \(L\): số công việc trung bình đang ở trong hệ thống.
- \(\lambda\): thông lượng trung bình, tính bằng công việc/giây.
- \(W\): thời gian trung bình một công việc ở trong hệ thống, tính bằng giây.

Đối với lời gọi đến dependency, có thể dùng:

\[
N_{\text{in-flight}} \approx \lambda_{\text{calls}} \times W_{\text{mean}}
\]

Ví dụ, Catalog nhận trung bình 400 lời gọi mỗi giây và mỗi lời gọi mất trung bình 250 ms, tương đương 0,25 giây:

\[
N = 400 \times 0.25 = 100
\]

Như vậy, Catalog có khoảng 100 lời gọi đang xử lý trung bình trong điều kiện tải ổn định. Con số này không phải giới hạn tối đa. Khi traffic tăng đột ngột hoặc độ trễ tăng, concurrency thực tế có thể cao hơn đáng kể.

Định luật Little áp dụng cho một hệ thống có dòng công việc và trạng thái ổn định trong khoảng đo. Hãy dùng throughput và thời gian trung bình cùng phạm vi đo. Nếu thời gian đo bao gồm cả thời gian xếp hàng, L cũng bao gồm công việc đang chờ; nếu chỉ muốn tính lời gọi đang thực thi ở dependency, hãy đo thời gian từ lúc gửi đến lúc hoàn tất ở đúng ranh giới đó.

## 3. Tính số lời gọi dependency từ request đầu vào

Một request nghiệp vụ có thể tạo nhiều lời gọi đến cùng dependency. Để ước lượng chính xác, cần tính số lần gọi trung bình trên mỗi request và ảnh hưởng của Retry.

Có thể dùng công thức:

\[
\lambda_{\text{dependency}} =
\lambda_{\text{requests}}
\times C_{\text{calls/request}}
\times A_{\text{attempts}}
\]

Trong đó:

- \(\lambda_{\text{requests}}\): tốc độ request đầu vào.
- \(C_{\text{calls/request}}\): số lần gọi dependency trung bình trên mỗi request.
- \(A_{\text{attempts}}\): số attempt trung bình cho mỗi lời gọi logic, đã tính Retry nếu có.

Ví dụ, API nhận 600 request/second. Mỗi request gọi Catalog trung bình 0,8 lần vì một số luồng không cần tra cứu sản phẩm. Retry làm số attempt trung bình tăng 10%, tức \(A_{\text{attempts}} = 1.1\):

\[
\lambda_{\text{catalog}} = 600 \times 0.8 \times 1.1 = 528
\]

Catalog thực tế nhận khoảng 528 attempts/second. Nếu chỉ dùng 600 RPS của API hoặc bỏ qua Retry, ước lượng sẽ sai.

Khi một request gọi nhiều dependency, hãy tính riêng từng dependency:

| Dependency | Calls/request | Attempts trung bình | Request đầu vào 600/s | Calls/s ước lượng |
|---|---:|---:|---:|---:|
| Catalog | 0,8 | 1,1 | 600 | 528 |
| Inventory | 0,6 | 1,0 | 600 | 360 |
| Pricing | 1,0 | 1,05 | 600 | 630 |

Nếu các lời gọi được chạy song song, tổng số lời gọi đang chạy trong ứng dụng là tổng concurrency của từng dependency. Thời gian hoàn tất request tổng thể có thể gần với lời gọi chậm nhất cộng các bước xử lý khác, chứ không nhất thiết bằng tổng latency của các dependency.

Nên đo attempt rate thực tế từ client metrics khi có thể. Công thức trên phù hợp để lập kế hoạch khi chưa có số liệu; Retry có backoff, retry có điều kiện hoặc request bị hủy có thể làm hệ số attempts thay đổi theo tải và loại lỗi.

## 4. Tính concurrency trung bình và dự phòng burst

Sau khi có call rate, nhân với latency trung bình để ước lượng concurrency trung bình. Sau đó dùng dữ liệu burst hoặc hệ số dự phòng để ước lượng tải cao điểm.

Ví dụ Catalog nhận 528 calls/second và latency trung bình là 180 ms:

\[
N_{\text{mean}} = 528 \times 0.18 = 95.04
\]

Con số này cho thấy khoảng 95 lời gọi đang in-flight trung bình. Nếu tải đỉnh cao hơn mức trung bình 1,4 lần, ước lượng sơ bộ cho burst là:

\[
N_{\text{burst}} \approx 95.04 \times 1.4 \approx 133
\]

Hệ số burst 1,4 trong ví dụ chỉ là giả định. Hãy thay bằng dữ liệu theo thời gian, chẳng hạn concurrency p95/p99, đỉnh theo phút hoặc kịch bản flash traffic. Không coi phép nhân hệ số burst là định luật; nó là cách lập ngân sách ban đầu cần được xác nhận bằng load test.

Cũng cần xem xét độ trễ tăng đồng thời với tải. Nếu dependency chuyển từ 180 ms lên 500 ms trong khi call rate vẫn là 528/s, concurrency trung bình theo Little sẽ tăng lên:

\[
N = 528 \times 0.5 = 264
\]

Đây là cơ chế khiến dependency chậm có thể tự làm số request đang chờ tăng lên. Khi thread, connection hoặc queue bị chiếm dụng, latency còn có thể tăng tiếp, tạo vòng xoáy quá tải.

## 5. Chia ngân sách concurrency cho từng instance

Ứng dụng thường chạy nhiều replica hoặc pod. Nếu traffic được phân phối đều, concurrency trung bình mỗi instance có thể ước lượng bằng tổng concurrency chia cho số instance khỏe mạnh:

\[
N_{\text{per-instance}} \approx
\frac{N_{\text{total}}}{R}
\]

Trong đó \(R\) là số instance đang nhận traffic. Với khoảng 133 lời gọi ở mức burst và sáu instance:

\[
N_{\text{per-instance}} \approx \frac{133}{6} \approx 22.2
\]

Đây chỉ là ước lượng khi traffic phân phối tương đối đều. Load balancer có thể phân phối không đồng đều, một instance có thể nhận nhiều request hơn vì kết nối dài, sticky routing, cache locality hoặc shard nóng. Nên đo concurrency theo từng instance và tính cả tình huống một replica không khỏe.

Khi autoscaling, tổng giới hạn đồng thời thay đổi theo số replica nếu Bulkhead được cấu hình cục bộ trên từng instance. Ví dụ, Bulkhead 24 lời gọi mỗi pod có nghĩa:

- 4 pod: tổng giới hạn lý thuyết 96.
- 6 pod: tổng giới hạn lý thuyết 144.
- 8 pod: tổng giới hạn lý thuyết 192.

Nếu backend chỉ chịu an toàn 150 lời gọi đồng thời, tăng số pod từ 6 lên 8 có thể khiến tổng giới hạn của ứng dụng vượt khả năng backend. Cần tính theo số pod tối đa, không chỉ số pod hiện tại. Nếu cần giới hạn toàn cụm, dùng cơ chế quota/concurrency phân tán hoặc giới hạn ở gateway/backend phù hợp; Bulkhead trong từng JVM thường chỉ áp dụng cục bộ.

## 6. Ước lượng năng lực phục vụ an toàn của dependency

Không thể suy ra concurrency an toàn chỉ từ latency. Cần xác định điểm mà dependency bắt đầu bão hòa thông qua load test và số liệu vận hành.

Các giới hạn cần xem xét gồm:

- CPU và bộ nhớ của dependency.
- Số worker thread hoặc event loop có thể xử lý.
- Connection pool của database và HTTP client.
- Giới hạn connection hoặc request đồng thời ở server.
- Queue depth và thời gian chờ trong queue.
- Giới hạn của dịch vụ dùng chung phía sau, như database, cache hoặc message broker.
- Độ trễ p95/p99 và error rate khi tăng tải.

Giả sử load test cho thấy Catalog bắt đầu tăng mạnh p99 và lỗi khi có khoảng 180 lời gọi đồng thời. Nhóm có thể chọn ngân sách bảo vệ thấp hơn, ví dụ 80%:

\[
C_{\text{budget}} = 180 \times 0.8 = 144
\]

144 là ngân sách concurrency mục tiêu cho toàn bộ các caller đã tính trong ví dụ, không phải giới hạn mặc định của Resilience4j. Phần còn lại tạo headroom cho biến động traffic, các client khác và hoạt động vận hành. Nếu Catalog còn nhận traffic từ các hệ thống khác, cần trừ phần tải của chúng trước khi cấp ngân sách cho ứng dụng này.

Một giới hạn an toàn phải được xác nhận bằng tải thực tế. Nếu backend thay đổi cấu hình, số replica, connection pool hoặc query profile, điểm bão hòa cũng có thể thay đổi.

## 7. Dùng Bulkhead để giới hạn số lời gọi đồng thời

Circuit Breaker và Bulkhead có vai trò khác nhau:

- Circuit Breaker theo dõi kết quả, tỷ lệ lỗi và lời gọi chậm để quyết định CLOSED, OPEN hoặc HALF_OPEN.
- Bulkhead giới hạn số tác vụ hoặc lời gọi được phép chạy đồng thời.
- TimeLimiter giới hạn thời gian chờ của thao tác.
- Connection pool giới hạn số kết nối có thể được sử dụng ở tầng client.

Khi Circuit Breaker ở CLOSED, nó có thể cho phép nhiều lời gọi cùng lúc. Nếu dependency chậm, các lời gọi tiếp tục chiếm connection và tài nguyên cho đến khi hoàn tất hoặc timeout. Bulkhead tạo giới hạn đồng thời để một dependency không chiếm hết tài nguyên dành cho các operation khác.

Ví dụ cấu hình Semaphore Bulkhead cho Catalog:

~~~yaml
resilience4j:
  bulkhead:
    instances:
      catalog:
        maxConcurrentCalls: 24
        maxWaitDuration: 0
~~~

Với cấu hình minh họa này, mỗi instance ứng dụng chỉ cho tối đa 24 lời gọi Catalog cùng lúc qua Bulkhead tương ứng. Khi hết slot, lời gọi mới bị từ chối thay vì xếp hàng chờ vô hạn. Ứng dụng có thể chuyển sang fallback hoặc trả lỗi quá tải theo chính sách.

Nếu sáu pod cùng có Bulkhead giới hạn 24, tổng giới hạn lý thuyết là 144. Phải tính số pod tối đa có thể hoạt động để không vượt ngân sách của backend. Nếu các pod có traffic lệch nhau, một pod có thể đầy Bulkhead trong khi pod khác còn slot; cần quan sát phân phối tải và cân nhắc giới hạn ở tầng dùng chung.

Thread-pool Bulkhead có thêm thread pool và queue riêng. Queue có thể hấp thụ burst ngắn, nhưng queue lớn làm tăng thời gian chờ và giữ request lâu hơn. Không nên dùng queue không giới hạn để che giấu tình trạng dependency không đủ năng lực.

## 8. Kết hợp Bulkhead với timeout và Circuit Breaker

Một chính sách bảo vệ thường cần cả ba cơ chế:

1. **Bulkhead** giới hạn số lời gọi được thực thi cùng lúc.
2. **TimeLimiter hoặc timeout của client** giới hạn thời gian chờ.
3. **Circuit Breaker** ngăn lời gọi mới khi thống kê cho thấy dependency suy giảm.

Ví dụ cấu hình các giới hạn cho Catalog:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      catalog:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 100
        minimumNumberOfCalls: 30
        failureRateThreshold: 50
        slowCallDurationThreshold: 500ms
        slowCallRateThreshold: 60
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 5

  bulkhead:
    instances:
      catalog:
        maxConcurrentCalls: 24
        maxWaitDuration: 0

  timelimiter:
    instances:
      catalog:
        timeoutDuration: 700ms
        cancelRunningFuture: true
~~~

Các giá trị là ví dụ cần điều chỉnh theo SLO và kết quả đo tải. **slowCallDurationThreshold** giúp Circuit Breaker nhận diện lời gọi chậm; **timeoutDuration** đặt thời hạn chờ; **maxConcurrentCalls** giới hạn lượng công việc đồng thời. Timeout 700 ms lớn hơn ngưỡng slow call 500 ms trong ví dụ để lời gọi có thể được nhận diện là chậm trước khi timeout, tùy cách tích hợp và thời điểm ghi nhận kết quả.

Khi Bulkhead hết slot, exception từ chối có thể xuất hiện trước khi lời gọi đến dependency. Cần phân loại lỗi này riêng với lỗi do backend. Nếu Circuit Breaker ghi nhận Bulkhead rejection như lỗi dependency, bộ ngắt có thể mở vì giới hạn cục bộ của caller. Cấu hình exception policy và thứ tự phối hợp phải phản ánh đúng ý nghĩa vận hành.

Khi Circuit Breaker OPEN, lời gọi mới bị từ chối trước khi tiêu thụ slot cho dependency. Khi HALF_OPEN, chỉ số probe được cấu hình được phép kiểm tra phục hồi. Bulkhead vẫn cần giới hạn tài nguyên trong lúc probe và các operation khác đang chạy.

## 9. Retry làm tăng concurrency và tải dependency

Retry có thể tăng số attempt trên mỗi request logic. Nếu một dependency lỗi tạm thời, nhiều request đồng thời có thể cùng retry, làm tải tăng đúng lúc backend đang suy giảm. Hiện tượng này có thể tạo retry storm.

Khi tính concurrency, phải dùng attempt rate chứ không chỉ logical request rate. Ví dụ 400 lời gọi logic mỗi giây và trung bình 1,5 attempt cho mỗi lời gọi sẽ tạo 600 attempts/second. Với latency trung bình 300 ms:

\[
N = 400 \times 1.5 \times 0.3 = 180
\]

Nếu bỏ qua Retry, ước lượng chỉ là 120 lời gọi và đánh giá thấp tải 50%.

Các nguyên tắc kiểm soát:

- Giới hạn **maxAttempts**.
- Chỉ retry lỗi có khả năng phục hồi và thao tác có thể lặp an toàn.
- Dùng backoff và jitter để phân tán thời điểm thử lại.
- Đặt timeout cho mỗi attempt và ngân sách thời gian tổng.
- Không retry liên tục khi Circuit Breaker đang OPEN.
- Theo dõi retry rate và số attempt thực tế theo dependency.

Với thao tác ghi, dùng idempotency key hoặc cơ chế tra cứu trạng thái để tránh thực hiện lặp nếu caller timeout sau khi server đã hoàn tất. Khi lập capacity plan, hãy cập nhật attempt factor theo dữ liệu production thay vì giữ cố định một hệ số giả định.

## 10. Lưu ý riêng với ứng dụng reactive

Reactive không tạo một thread riêng cho mỗi request, nhưng không có nghĩa số lời gọi đồng thời là vô hạn hoặc miễn phí. Mỗi request đang chờ vẫn có thể chiếm connection, socket, buffer, bộ nhớ, subscription và slot xử lý ở dependency. Khi số Publisher đang in-flight tăng cao, ứng dụng vẫn có thể cạn connection pool hoặc làm backend quá tải.

Trong một luồng xử lý batch, Reactor cho phép giới hạn số phần tử được xử lý đồng thời bằng concurrency của **flatMap**:

~~~java
Flux<Product> products =
    Flux.fromIterable(productIds)
        .flatMap(catalogClient::getProduct, 24);
~~~

Tham số 24 giới hạn số inner Publisher đồng thời trong lần xử lý Flux này. Nó không phải giới hạn toàn cục cho tất cả request HTTP của ứng dụng. Nếu có 100 request độc lập, mỗi request tạo một Flux với concurrency 24, tổng số lời gọi có thể lớn hơn nhiều. Muốn có giới hạn dùng chung giữa các request, cần Bulkhead hoặc semaphore/connection pool có phạm vi chia sẻ phù hợp.

Trong WebFlux:

- Dùng reactive Circuit Breaker factory và giữ Mono/Flux trong pipeline.
- Dùng timeout của Reactor hoặc client theo ngân sách của operation.
- Tránh gọi **block()** trên event loop.
- Giới hạn concurrency tại phạm vi thực sự cần bảo vệ, không chỉ trong một batch riêng lẻ.
- Theo dõi số request đang in-flight, connection pool, pending acquire và cancellation.
- Kiểm tra connector có truyền cancellation xuống request mạng hay không.

Backpressure giúp điều tiết việc phát và tiêu thụ phần tử trong một pipeline, nhưng không tự tạo giới hạn toàn cục cho mọi lời gọi đến một dependency. Cần kết hợp đúng cơ chế theo phạm vi tải.

## 11. Đọc số liệu để nhận biết điểm bão hòa

Không nên chỉ theo dõi CPU. Một dependency có thể bị giới hạn bởi connection pool, database hoặc queue trong khi CPU vẫn chưa cao. Hãy kết hợp nhiều tín hiệu:

| Tín hiệu | Dấu hiệu cần chú ý | Hành động điều tra |
|---|---|---|
| Calls/s | Tăng nhanh hoặc vượt baseline | Kiểm tra traffic, fan-out và Retry |
| In-flight calls | Tăng liên tục dù throughput không tăng | Kiểm tra latency, queue và request bị treo |
| p95/p99 latency | Tăng mạnh khi tải tăng | Tìm điểm bão hòa và bottleneck |
| Error/timeout rate | Tăng đồng thời với latency | Kiểm tra dependency, network và timeout |
| Connection pool usage | Chạm max hoặc pending acquire tăng | Xem pool size, thời gian giữ connection và client timeout |
| Bulkhead rejection | Tăng theo burst hoặc latency | Xem giới hạn concurrency và khả năng backend |
| Circuit Breaker state | Chuyển OPEN thường xuyên | Kiểm tra failure/slow-call rate và cửa sổ |
| Queue depth | Tăng nhưng không giảm | Giảm admission, giới hạn queue hoặc tăng năng lực có kiểm chứng |

Một mẫu nguy hiểm là throughput hoàn tất gần như đứng yên, trong khi in-flight và latency tăng. Điều đó cho thấy công việc đang tích tụ nhanh hơn khả năng hoàn tất. Tăng số request được nhận vào có thể làm hàng đợi dài thêm mà không cải thiện thông lượng.

Cần quan sát cả số liệu theo từng pod và toàn cụm. Metric tổng hợp có thể che giấu một pod nóng, một shard chậm hoặc một connection pool cạn cục bộ.

## 12. Ví dụ ước lượng từ đầu đến cuối

Một API đặt hàng chạy sáu pod Gateway và gọi Catalog. Các số liệu đo được trong giờ cao điểm:

- Request đầu vào: 600 requests/second.
- Tỷ lệ request gọi Catalog: trung bình 0,8 lần/request.
- Retry attempts trung bình: 1,1 lần cho mỗi lời gọi logic.
- Latency trung bình của Catalog: 180 ms.
- Load test cho thấy Catalog bắt đầu bão hòa ở khoảng 180 lời gọi đồng thời.
- Nhóm giữ lại 20% năng lực làm headroom cho biến động và traffic khác.

**Bước 1: Tính attempt rate đến Catalog**

\[
\lambda = 600 \times 0.8 \times 1.1 = 528 \text{ calls/s}
\]

**Bước 2: Tính concurrency trung bình**

\[
N_{\text{mean}} = 528 \times 0.18 \approx 95
\]

**Bước 3: Ước lượng burst**

Nếu burst factor quan sát được là 1,4:

\[
N_{\text{burst}} \approx 95 \times 1.4 \approx 133
\]

**Bước 4: Tính ngân sách concurrency an toàn**

\[
C_{\text{budget}} = 180 \times (1 - 0.20) = 144
\]

**Bước 5: Chia giới hạn cho sáu pod**

\[
C_{\text{pod}} = \frac{144}{6} = 24
\]

Nhóm có thể bắt đầu kiểm thử với Semaphore Bulkhead tối đa 24 lời gọi Catalog trên mỗi pod. Tổng giới hạn lý thuyết là 144 khi có đủ sáu pod. Con số burst 133 thấp hơn ngân sách 144, nhưng khoảng dự phòng không lớn; cần theo dõi tải lệch và tình huống một replica không hoạt động.

Nếu hệ thống autoscale lên tám pod mà vẫn giữ 24 slot mỗi pod, tổng giới hạn trở thành 192 và vượt ngân sách 144. Khi thay đổi số replica tối đa, phải tính lại giới hạn mỗi pod hoặc dùng giới hạn toàn cục. Nếu một pod bị mất, tổng khả năng admission cũng giảm; hệ thống cần chấp nhận từ chối có kiểm soát hoặc có kế hoạch năng lực dự phòng thay vì gửi quá tải sang năm pod còn lại.

Các phép tính trên là điểm khởi đầu. Load test với traffic mix, độ trễ và tỷ lệ Retry thực tế mới xác nhận được Bulkhead có phù hợp hay không.

## 13. Quy trình đo và hiệu chỉnh trong thực tế

Có thể tiến hành theo trình tự sau:

1. **Xác định ranh giới đo:** chọn API, dependency và operation cần bảo vệ.
2. **Thu thập baseline:** đo RPS, calls/s, latency trung bình, p95/p99, error rate và in-flight concurrency.
3. **Tính call amplification:** xác định số lời gọi trên mỗi request và attempt factor do Retry.
4. **Ước lượng concurrency:** dùng attempt rate nhân latency trung bình theo định luật Little.
5. **Đo điểm bão hòa:** tăng tải có kiểm soát trong load test và quan sát throughput, latency, queue, connection pool cùng tài nguyên.
6. **Đặt ngân sách:** dành headroom cho burst, traffic khác và biến động phân phối.
7. **Chọn Bulkhead:** tính giới hạn theo tổng năng lực và số replica tối đa; xác định hành vi khi hết slot.
8. **Chọn timeout và Circuit Breaker thresholds:** dựa trên SLO, latency distribution và lỗi thực tế.
9. **Kiểm thử sự cố:** làm dependency chậm, lỗi, hết connection hoặc mở Circuit Breaker; xác nhận fallback và admission control.
10. **Hiệu chỉnh sau triển khai:** so sánh metric thực tế với ước lượng, cập nhật khi traffic mix hoặc kiến trúc thay đổi.

Không tăng Bulkhead chỉ vì thấy rejection. Trước tiên hãy xác định backend còn năng lực hay không. Nếu dependency đã bão hòa, tăng giới hạn chỉ chuyển thêm công việc vào một hàng đợi đang tắc. Ngược lại, nếu backend còn dư năng lực nhưng Bulkhead quá thấp, có thể tăng dần và đo lại.

## 14. Những lỗi ước lượng thường gặp

1. **Dùng API RPS thay cho dependency call rate.** Bỏ qua fan-out khiến tính thiếu số lời gọi.
2. **Bỏ qua Retry.** Attempt rate có thể cao hơn đáng kể so với số lời gọi logic.
3. **Dùng p99 thay cho latency trung bình trong công thức Little mà không hiểu mục đích.** Little dùng thời gian trung bình; percentile cao hữu ích cho timeout và kiểm tra tail latency.
4. **Chia concurrency cho số replica hiện tại mà quên autoscaling.** Tổng giới hạn cục bộ có thể vượt năng lực backend khi số pod tăng.
5. **Coi Circuit Breaker là giới hạn đồng thời.** Khi CLOSED, nhiều lời gọi vẫn có thể chạy cùng lúc; cần Bulkhead hoặc giới hạn client.
6. **Đặt queue quá lớn.** Queue che giấu quá tải nhưng làm tăng latency và thời gian giữ request.
7. **Chỉ nhìn CPU.** Connection pool, database, thread, event loop hoặc network có thể là bottleneck trước CPU.
8. **Dùng concurrency của flatMap làm giới hạn toàn cục.** Giới hạn đó thường chỉ áp dụng cho một subscription, không tự chia sẻ giữa tất cả request.
9. **Không tính traffic từ client khác.** Ngân sách của một ứng dụng phải nằm trong năng lực còn lại của dependency.
10. **Không đo lại sau thay đổi.** Tăng replica, đổi timeout, Retry hoặc payload có thể thay đổi latency và concurrency.

## Kết luận

Ước lượng số lời gọi đồng thời bằng cách đo attempt rate đến dependency và latency trung bình, sau đó áp dụng định luật Little: \(N \approx \lambda \times W\). Dùng load test để xác định điểm bão hòa, dành headroom và tính giới hạn theo số replica tối đa. Circuit Breaker phát hiện dependency suy giảm và ngăn lời gọi khi OPEN; Bulkhead giới hạn concurrency, timeout giới hạn thời gian chờ, còn Retry có thể làm tăng tải. Kết hợp các cơ chế với metric theo từng dependency và từng instance giúp ứng dụng duy trì khả năng phục vụ khi traffic tăng hoặc dependency chậm.
