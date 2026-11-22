# Hiểu autoscaling, burst traffic và tốc độ cấp instance

Autoscaling giúp nền tảng serverless tăng hoặc giảm số execution environment/instance theo nhu cầu. Khi traffic tăng, nền tảng khởi tạo thêm capacity để xử lý request hoặc message song song; khi traffic giảm, capacity dư được thu hồi. Cơ chế này giảm việc phải tự vận hành máy chủ, nhưng không có nghĩa năng lực tăng lên tức thì hoặc vô hạn.

Ba yếu tố cần phân biệt là **mức concurrency cần thiết**, **tốc độ nền tảng cấp thêm instance** và **thời gian một instance mới sẵn sàng xử lý request**. Một hệ thống có thể có giới hạn concurrency đủ lớn nhưng vẫn gặp throttling hoặc latency cao trong một burst đột ngột vì capacity cần thời gian để khởi tạo. Java function còn có thể chịu cold start do JVM, class loading, dependency injection và khởi tạo SDK.

Trong module **CLOUD_SERVERLESS**, người học phát triển Java function kích hoạt bởi HTTP, message hoặc event, đồng thời xử lý trạng thái, quyền truy cập, retry, idempotency, cold start, mở rộng và chi phí. Bài này giải thích autoscaling, burst traffic, tốc độ cấp instance, các giới hạn điều tiết tải và cách kiểm thử capacity trước production.

## 1. Autoscaling hoạt động như thế nào?

Autoscaling là quá trình điều chỉnh capacity theo tải quan sát được. Với FaaS, provider thường quản lý execution environment và số invocation chạy song song. Với nền tảng container serverless, autoscaler có thể điều chỉnh số instance/container dựa trên request concurrency, CPU, memory hoặc tín hiệu khác.

Một vòng autoscaling khái quát:

~~~mermaid
flowchart TD
    A[Incoming requests / messages] --> B[Measure demand]
    B --> C{Capacity available?}
    C -->|Yes| D[Route to ready instances]
    C -->|No| E[Request more capacity]
    E --> F[Provision and initialize]
    F --> G[Ready instances]
    G --> D
    D --> H[Process work]
    H --> I[Observe load and latency]
    I --> B
    I --> J{Demand stays low?}
    J -->|Yes| K[Scale in after policy delay]
    J -->|No| B
~~~

Autoscaler thường không chỉ nhìn một request riêng lẻ. Nó sử dụng tín hiệu như số request đang chờ, concurrency, CPU, queue backlog, số message chưa xử lý hoặc mức sử dụng instance. Sau đó, policy quyết định khi nào scale out, tăng bao nhiêu capacity và khi nào scale in.

Các bước đo tải, quyết định và cấp instance đều có độ trễ. Vì vậy, thiết kế cần tính đến khoảng thời gian trước khi capacity mới sẵn sàng, đặc biệt khi traffic tăng nhanh hơn khả năng scale-out.

## 2. Phân biệt request rate, concurrency, throughput và instance count

Các khái niệm này có liên quan nhưng không thể thay thế nhau:

| Khái niệm | Ý nghĩa | Đơn vị thường dùng |
|---|---|---|
| Request rate | Số request đến trong một đơn vị thời gian | requests/second (RPS) |
| Concurrency | Số request hoặc invocation đang chạy cùng thời điểm | concurrent requests/invocations |
| Throughput | Số công việc hoàn tất trong một đơn vị thời gian | requests/second, messages/second |
| Instance count | Số execution environment hoặc container instance đang hoạt động | instances |
| Provisioning rate | Tốc độ tạo và đưa instance mới vào trạng thái sẵn sàng | instances/second |
| Startup latency | Thời gian từ lúc bắt đầu khởi tạo đến khi instance sẵn sàng | milliseconds/seconds |

Ví dụ, 100 RPS không nhất thiết cần 100 instance. Nếu mỗi request hoàn tất trong 100 ms và instance có thể xử lý một request tại một thời điểm, concurrency trung bình xấp xỉ 10. Nếu một container có thể xử lý 10 request đồng thời, số container cần thiết có thể thấp hơn nữa, tùy CPU, memory và hiệu năng ứng dụng.

Với AWS Lambda, một execution environment thông thường xử lý một invocation tại một thời điểm; scale concurrency thường đồng nghĩa cần thêm execution environment. Với container serverless như Cloud Run, một instance có thể nhận nhiều request đồng thời theo cấu hình concurrency và khả năng thread-safe của ứng dụng. Không áp dụng một phép quy đổi instance/concurrency cho mọi nền tảng.

## 3. Ước lượng concurrency bằng Little’s Law

Một ước lượng ban đầu hữu ích là:

\[
C \approx \lambda \times W
\]

Trong đó:

- \(C\): số request đang xử lý trung bình (concurrency).
- \(\lambda\): tốc độ request đến, tính theo request/giây.
- \(W\): thời gian xử lý trung bình, tính bằng giây.

Ví dụ API nhận 400 RPS và thời gian xử lý trung bình là 250 ms:

\[
C \approx 400 \times 0.25 = 100
\]

Hệ thống cần khoảng 100 request đang chạy đồng thời trong điều kiện ổn định. Nếu muốn có headroom cho biến động, có thể thử nghiệm ở mức 120–150 concurrency rồi đo lại; hệ số dự phòng phải dựa trên SLA, phân phối latency và giới hạn downstream, không phải con số cố định cho mọi hệ thống.

### Vì sao không dùng mỗi average?

Average có thể che khuất tail latency. Nếu phần lớn request mất 100 ms nhưng một số request mất 3 giây, p95/p99 có thể cao hơn nhiều. Những request chậm giữ slot concurrency lâu hơn, khiến số request đang chạy tăng ngay cả khi RPS không đổi.

Cần đo tối thiểu:

- RPS theo thời gian và theo route.
- Duration p50, p95, p99.
- Concurrent requests/invocations.
- Tỷ lệ timeout, 429, 5xx và throttling.
- CPU, memory, connection pool và dependency latency.
- Queue backlog/oldest message age đối với async workload.

Với hệ thống nhiều loại request, tính capacity theo từng nhóm route hoặc workload class. Một endpoint gọi database chậm có thể cần nhiều concurrency hơn endpoint chỉ trả cache.

## 4. Concurrency không đồng nghĩa throughput

Concurrency đo số việc đang chạy cùng lúc; throughput đo số việc hoàn tất trong một đơn vị thời gian. Nếu request duration tăng, cùng một concurrency sẽ tạo throughput thấp hơn.

Ví dụ:

| Concurrency | Duration trung bình | Throughput lý thuyết gần đúng |
|---:|---:|---:|
| 50 | 100 ms | 500 RPS |
| 50 | 250 ms | 200 RPS |
| 50 | 1 s | 50 RPS |

Đây là phép ước lượng cho workload ổn định, không phải benchmark. CPU saturation, lock contention, downstream limits và batching có thể làm throughput thấp hơn.

Một hệ thống scale-out khi latency tăng có thể không cải thiện throughput nếu mọi instance đều chờ cùng một database đang quá tải. Khi đó, thêm function chỉ tăng số connection và cạnh tranh tài nguyên. Autoscaling cần được phối hợp với giới hạn downstream.

## 5. Scale-out và scale-in

**Scale-out** tăng số execution environment/instance khi tải vượt capacity hiện tại. **Scale-in** giảm capacity khi nhu cầu giảm trong một khoảng thời gian.

Scale-out nhanh giúp hấp thụ burst, nhưng khởi tạo quá nhiều instance cùng lúc có thể gây:

- Cold start tăng.
- Nhiều kết nối đồng thời đến database.
- Áp lực lên secret manager, cache hoặc API bên ngoài.
- Throttling do quota.
- Chi phí tăng đột biến.

Scale-in quá nhanh có thể làm hệ thống dao động: capacity bị thu hồi, traffic tăng lại, rồi phải khởi tạo từ đầu. Với workload có thời gian xử lý dài hoặc queue consumer, scale-in còn cần bảo đảm request/message đang xử lý được hoàn tất hoặc có thể retry an toàn.

Autoscaler thường có ngưỡng, cửa sổ đo, cooldown hoặc stabilization policy để tránh thay đổi capacity liên tục. Tên và semantics của các tham số phụ thuộc provider.

## 6. Tốc độ cấp instance khác với giới hạn concurrency

Một hệ thống có thể cho phép tối đa 1.000 concurrent invocations nhưng không cấp đủ 1.000 execution environment trong cùng một thời điểm. Giới hạn concurrency mô tả mức tối đa được phép; provisioning rate mô tả tốc độ thêm capacity theo thời gian.

Mô hình khái quát:

- \(C_{target}\): concurrency cần đạt.
- \(K\): số request đồng thời mà một instance có thể xử lý hiệu quả.
- \(N_{target}\): số instance cần thiết.
- \(R_p\): tốc độ provision instance mới.
- \(T_i\): thời gian khởi tạo một instance mới.

Ước lượng số instance:

\[
N_{target} \approx \left\lceil \frac{C_{target}}{K} \right\rceil
\]

Nếu cần tăng từ \(N_{current}\) lên \(N_{target}\), số instance cần bổ sung là:

\[
\Delta N = \max(0, N_{target} - N_{current})
\]

Trong một mô hình tuyến tính rất đơn giản, thời gian cấp thêm capacity có thể xấp xỉ:

\[
T_{scale} \approx \frac{\Delta N}{R_p} + T_i
\]

Đây chỉ là mô hình tư duy. Provider có thể dùng nhiều pool, mức burst allowance, quota theo Region, thuật toán scale phi tuyến và nhiều bước khởi tạo. Không suy ra provisioning rate cố định nếu provider không công bố hoặc nếu chưa đo trong đúng account/Region.

### Ví dụ

Một container xử lý hiệu quả 8 request đồng thời. Ứng dụng cần tăng từ 5 lên 45 instance, tức thêm 40 instance. Nếu phép đo trong môi trường thử nghiệm cho thấy hệ thống thường cấp được 10 instance/giây và startup mất trung bình 0,8 giây, thời gian lý thuyết gần đúng là:

\[
T_{scale} \approx \frac{40}{10} + 0.8 = 4.8 \text{ giây}
\]

Trong thực tế, thời gian có thể dài hơn do quota, scheduling, image pull, JVM initialization, network setup và downstream readiness. Vì vậy, burst cần được kiểm thử chứ không chỉ tính trên giấy.

## 7. Burst traffic, ramp traffic và sustained traffic

Không phải mọi đợt tăng traffic đều giống nhau:

| Dạng tải | Mô tả | Rủi ro chính |
|---|---|---|
| Burst/spike | Tăng rất nhanh trong vài giây | Capacity chưa kịp provision |
| Ramp-up | Tăng đều theo thời gian | Scale-out chậm hơn tốc độ tăng tải |
| Sustained peak | Giữ tải cao trong thời gian dài | Quota, downstream và chi phí |
| Periodic peak | Tăng theo giờ/ngày hoặc lịch sự kiện | Baseline capacity không đủ trước giờ cao điểm |
| Flash crowd | Nhiều client cùng truy cập do một sự kiện | Thundering herd và retry storm |
| Sudden drop | Tải giảm nhanh sau peak | Scale-in trễ, capacity dư và chi phí |

Một hệ thống chịu được 500 RPS ổn định chưa chắc chịu được cú nhảy từ 20 lên 500 RPS trong 100 ms. Trong trường hợp đầu, autoscaler có thời gian quan sát và mở rộng. Trong trường hợp sau, request có thể đến trước khi capacity mới sẵn sàng.

### Đường tải minh họa

~~~mermaid
xychart-beta
    title "Ba kiểu tăng traffic"
    x-axis ["t0", "t1", "t2", "t3", "t4", "t5"]
    y-axis "Relative load" 0 --> 100
    line [10, 12, 20, 35, 55, 70]
    line [10, 10, 95, 95, 20, 10]
    line [10, 25, 45, 65, 85, 100]
~~~

Đồ thị chỉ minh họa hình dạng tải. Khi thiết kế, dùng traffic profile thật từ access log, campaign calendar hoặc load test để xác định spike magnitude, ramp rate và thời gian peak.

## 8. Vì sao burst gây throttling dù còn quota?

Giả sử function đang có 20 execution environment sẵn sàng. Traffic tăng đột ngột khiến concurrency cần 500. Nếu platform chỉ bổ sung capacity theo một tốc độ nhất định và mỗi environment cần thời gian khởi tạo, một phần request có thể đến trước khi capacity mới sẵn sàng.

Những request này có thể:

- Chờ trong hàng đợi nội bộ của gateway nếu dịch vụ hỗ trợ.
- Nhận throttling hoặc 429/503.
- Timeout ở client trước khi function bắt đầu.
- Được retry bởi client hoặc event source.
- Tạo tải lặp khi nhiều client retry cùng lúc.

Retry có thể làm burst nặng hơn. Nếu 500 request thất bại đều được client retry ngay, hệ thống có thể nhận thêm một đợt tương tự khi đang thiếu capacity. Dùng exponential backoff, jitter, retry budget và idempotency để hạn chế hiệu ứng này.

Không xem throttling chỉ là lỗi cần tăng concurrency. Hãy xác định request bị chặn ở API gateway, account quota, function concurrency, event source mapping hay dependency.

## 9. Cold start và tốc độ sẵn sàng của Java function

Cold start là khoảng thời gian cần để tạo execution environment mới và đưa ứng dụng vào trạng thái nhận request. Với Java, các công việc khởi tạo có thể gồm:

- Khởi tạo runtime/JVM.
- Nạp class và resolve dependency.
- Khởi tạo dependency injection container.
- Tạo client cho database, queue, object storage và secret manager.
- Đọc cấu hình, certificate hoặc schema.
- JIT compilation và warm-up một số đường code.
- Thiết lập network connection.

Cold start phụ thuộc runtime, artifact size, framework, memory/CPU được cấp, cách khởi tạo và nền tảng. Không thể kết luận Java luôn chậm hơn mọi ngôn ngữ; cần đo trong cùng workload và deployment configuration.

### Giảm thời gian khởi tạo

- Giữ dependency ở mức cần thiết; tránh kéo cả framework lớn cho một handler nhỏ.
- Khởi tạo client dùng chung ngoài handler khi runtime cho phép tái sử dụng environment.
- Tránh gọi nhiều service đồng bộ trong static initializer nếu không bắt buộc.
- Dùng connection pool có kích thước phù hợp và quản lý timeout.
- Giảm kích thước artifact, loại bỏ dependency không dùng.
- Chọn memory/CPU phù hợp rồi benchmark.
- Dùng Java runtime optimization hoặc snapshot feature nếu provider hỗ trợ và workload phù hợp.
- Đo init duration riêng với business duration.

Khởi tạo client ngoài handler có thể giảm overhead cho invocation tiếp theo, nhưng environment có thể bị thu hồi bất cứ lúc nào. Không lưu trạng thái nghiệp vụ duy nhất trong static field hoặc filesystem tạm.

## 10. Warm capacity, minimum instances và provisioned concurrency

Có một số cách duy trì capacity sẵn sàng:

- **Minimum instances/min replicas:** giữ một số container instance tối thiểu hoạt động.
- **Provisioned concurrency:** provider chuẩn bị trước một số execution environment đã khởi tạo cho function/alias/version.
- **Scheduled scaling:** tăng baseline trước giờ cao điểm theo lịch.
- **Pre-warming:** gửi traffic hoặc tác vụ chuẩn bị trước khi peak đến, nếu platform và chính sách cho phép.

Provisioned/warm capacity giúp giảm xác suất request phải chờ cold start, nhưng không bảo đảm mọi request đều không có latency. Khi tải vượt mức warm capacity, request dư vẫn có thể cần scale-out bình thường. Network, dependency và application processing vẫn có thể chậm.

### Ví dụ Terraform cho AWS Lambda

~~~hcl
resource "aws_lambda_function" "orders" {
  function_name = "orders-api"
  role          = aws_iam_role.lambda_exec.arn
  runtime       = "java21"
  handler       = "com.example.OrderHandler"
  filename      = "build/orders.zip"
  publish       = true

  # Giới hạn concurrency tối đa dành cho function.
  reserved_concurrent_executions = 120
}

resource "aws_lambda_alias" "live" {
  name             = "live"
  function_name    = aws_lambda_function.orders.function_name
  function_version = aws_lambda_function.orders.version
}

resource "aws_lambda_provisioned_concurrency_config" "live" {
  function_name                     = aws_lambda_function.orders.function_name
  qualifier                         = aws_lambda_alias.live.name
  provisioned_concurrent_executions = 30
}
~~~

Đây là ví dụ minh họa. Alias cần trỏ đến published version hợp lệ; Terraform resource/function version phải được tổ chức theo quy trình release của project. Reserved concurrency giới hạn tổng concurrency của function, trong khi provisioned concurrency giữ trước một phần environment đã khởi tạo. Hai giới hạn phải được tính cùng nhau và theo quota account/Region.

### Warm-up không phải bảo đảm

Gửi request định kỳ để “giữ nóng” một function không bảo đảm request production sẽ chạy trên đúng environment đó. Platform có thể tạo environment khác, thu hồi environment cũ hoặc route traffic theo cách riêng. Warm-up còn tiêu thụ invocation và có thể tạo chi phí. Dùng tính năng capacity chính thức nếu cần latency có thể dự đoán.

## 11. Giới hạn concurrency và admission control

Autoscaling cần có giới hạn để bảo vệ hệ thống. Các cơ chế thường gặp:

- **Account/Region concurrency quota:** tổng số invocation đồng thời được phép trong account/Region.
- **Reserved concurrency:** dành hoặc giới hạn concurrency của một function trên nền tảng hỗ trợ.
- **Maximum instances:** giới hạn số instance của service/container.
- **Maximum concurrency per instance:** giới hạn request đồng thời trên mỗi container.
- **Event source maximum concurrency:** giới hạn số consumer concurrency từ queue/stream nếu source hỗ trợ.
- **API rate limit:** giới hạn tốc độ request theo client, route hoặc tenant.
- **Admission control:** từ chối hoặc trì hoãn request trước khi hệ thống quá tải.

Một cap thấp giúp bảo vệ database nhưng có thể khiến backlog hoặc throttling tăng. Một cap cao giúp scale nhanh nhưng có thể làm downstream sụp đổ. Chọn giới hạn theo capacity thực tế của toàn bộ dependency chain.

### Ví dụ giới hạn instance cho container serverless

Với nền tảng container serverless, có thể cấu hình minimum và maximum instance count, cùng concurrency mỗi instance. Tên cấu hình khác nhau giữa provider. Nguyên tắc là tính:

\[
C_{max} \approx N_{max} \times K_{instance}
\]

Trong đó \(K_{instance}\) là concurrency hiệu quả đã benchmark, không nhất thiết bằng cấu hình concurrency tối đa. Nếu ứng dụng Java có lock toàn cục hoặc pool database nhỏ, concurrency hiệu quả có thể thấp hơn nhiều.

## 12. Rate limiting và token bucket

Rate limiting điều tiết tốc độ request trước khi chúng làm quá tải function hoặc dependency. Token bucket là một mô hình phổ biến:

- Bucket chứa tối đa \(B\) token.
- Token được bổ sung với tốc độ \(r\) token/giây.
- Mỗi request cần một hoặc nhiều token.
- Khi bucket hết token, request bị delay hoặc từ chối theo policy.

Bucket cho phép một burst ngắn tối đa theo dung lượng \(B\), trong khi giữ tốc độ trung bình gần \(r\).

Ví dụ tenant được phép trung bình 100 request/giây với burst capacity 200. Một đợt 150 request tức thời có thể được chấp nhận nếu bucket đang đầy; request vượt khả năng sẽ bị giới hạn hoặc xếp hàng.

Rate limit nên có nhiều lớp:

1. Edge/API gateway để chặn traffic không hợp lệ sớm.
2. Per-tenant hoặc per-client quota để tránh một khách hàng chiếm capacity.
3. Function concurrency cap để bảo vệ execution budget.
4. Dependency-specific limit để không vượt database hoặc provider quota.

Khi từ chối HTTP request, trả status và retry guidance phù hợp, thường dùng 429 cho rate limit của client. Với overload tạm thời ở hệ thống, 503 có thể phù hợp. Không trả 200 giả rồi âm thầm bỏ request.

## 13. Queue buffering để hấp thụ burst

Đối với công việc không cần phản hồi đồng bộ ngay lập tức, queue giúp tách tốc độ nhận request khỏi tốc độ xử lý. Producer ghi message nhanh, consumer xử lý theo capacity có kiểm soát.

~~~mermaid
flowchart LR
    A[Traffic burst] --> B[API / Producer]
    B --> C[Durable queue]
    C --> D[Consumer scaling policy]
    D --> E[Java functions]
    E --> F[Database / downstream]
    C --> G[Backlog and age metrics]
    G --> D
~~~

Queue không xóa tải; nó chuyển tải thành backlog. Nếu producer gửi nhanh hơn consumer xử lý trong thời gian dài, backlog sẽ tăng liên tục.

Nếu tốc độ đến là \(\lambda\) message/giây và tốc độ xử lý tổng là \(\mu\) message/giây:

- Khi \(\mu > \lambda\), consumer có thể xử lý backlog đã tích lũy.
- Khi \(\mu = \lambda\), backlog không giảm đáng kể.
- Khi \(\mu < \lambda\), backlog tiếp tục tăng.

Nếu backlog có \(B_q\) message và capacity xử lý vượt incoming rate là \(\mu-\lambda\), thời gian dọn backlog gần đúng:

\[
T_{drain} \approx \frac{B_q}{\mu-\lambda}
\]

Công thức giả định tốc độ ổn định, không có lỗi/retry và không bị giới hạn khác. Theo dõi oldest message age, queue depth, receive count, DLQ và throughput thay vì chỉ nhìn số message hiện có.

### Queue không phù hợp cho mọi request

Nếu client cần kết quả ngay, việc đưa request vào queue có thể thay đổi contract từ synchronous sang asynchronous. Có thể trả 202 Accepted cùng operation ID và cung cấp endpoint truy vấn trạng thái. Đừng trả kết quả thành công cuối cùng khi message mới chỉ được enqueue.

## 14. Điều tiết concurrency cho queue consumer

Queue consumer có thể scale theo backlog. Nhưng scale-out quá nhanh có thể khiến hàng trăm function cùng mở database connection hoặc gọi API bên ngoài.

Cần giới hạn consumer concurrency dựa trên:

- Capacity tối đa của database.
- Connection pool và proxy.
- Rate limit của external provider.
- Batch size và thời gian xử lý mỗi message.
- Visibility timeout hoặc lock duration.
- Retry và DLQ policy.
- Ordering/partition constraints.

Ví dụ, database chịu được tối đa 300 connection ứng dụng, nhưng các service khác đã dùng 180. Nếu mỗi function environment có pool 5 connection, giới hạn lý thuyết cho worker chỉ còn 24 environment, chưa tính connection admin/monitoring và headroom. Pool nhỏ hơn hoặc proxy có thể cho phép nhiều function hơn, nhưng phải đo.

Đối với AWS Lambda + SQS, có thể dùng reserved concurrency để cap function và maximum concurrency trên event source mapping khi loại queue/provider hỗ trợ. Hai giá trị cần được cấu hình nhất quán: event source không nên đòi concurrency cao hơn cap của function nếu mục tiêu là tránh throttling.

## 15. Bảo vệ database và dependency khi scale-out

Một hệ thống serverless có thể tạo nhiều instance hơn mô hình server truyền thống. Điều đó không có nghĩa database tự động scale tương ứng.

Ví dụ, 200 Lambda environments mỗi environment mở pool 10 connection có thể tạo ra tối đa khoảng 2.000 connection nếu tất cả pool cùng hoạt động. Database có thể hết connection trước khi function đạt concurrency mong muốn.

Các biện pháp:

- Dùng pool nhỏ, có giới hạn rõ ràng.
- Đóng/giải phóng connection đúng cách.
- Cân nhắc connection proxy/pooling service.
- Dùng cache cho dữ liệu đọc lặp lại nếu phù hợp.
- Batch write/read khi nghiệp vụ cho phép.
- Giới hạn concurrency ở tầng function hoặc event source.
- Dùng timeout ngắn hợp lý và circuit breaker.
- Tách workload nặng sang queue.
- Theo dõi connection count, wait time, lock, CPU và IOPS của database.

Đừng tăng max instances chỉ vì CPU của function thấp. Function có thể đang chờ database hoặc external API. Scale-out khi bottleneck ở dependency sẽ làm tăng áp lực mà không tăng throughput.

## 16. Autoscaling theo tín hiệu nào?

Autoscaler có thể dùng nhiều loại tín hiệu:

| Tín hiệu | Phù hợp với | Hạn chế |
|---|---|---|
| Concurrent requests | HTTP service và FaaS | Không phản ánh đầy đủ độ nặng của từng request |
| Requests per instance | Container HTTP | Cần benchmark concurrency hiệu quả |
| CPU utilization | Workload CPU-bound | Có thể phản ứng chậm với I/O-bound traffic |
| Memory utilization | Workload memory-bound | Không cho biết request queueing trực tiếp |
| Queue depth | Async consumer | Queue depth không thể hiện tuổi backlog nếu message đến liên tục |
| Oldest message age | Queue có SLA thời gian | Cần đo đúng source metric |
| Custom business metric | Workload đặc thù | Cần tránh metric cardinality cao và feedback loop khó hiểu |

Với HTTP function, API gateway có thể cần rate limit và throttling riêng trước khi request đến function. Với queue consumer, queue depth và oldest age thường hữu ích hơn CPU đơn lẻ. Với workflow, số execution đang chạy, thời gian ở từng step và retry count giúp phát hiện điểm nghẽn.

## 17. Scale-in và graceful shutdown

Khi tải giảm, platform có thể thu hồi execution environment. Ứng dụng không nên giả định instance sẽ tồn tại lâu hoặc luôn nhận được thông báo shutdown đủ sớm để hoàn tất mọi công việc.

Thiết kế an toàn:

- Không giữ state nghiệp vụ duy nhất trong memory.
- Commit tiến trình trước khi xác nhận message hoặc trả success.
- Đóng connection/resource nếu runtime cung cấp lifecycle hook.
- Dùng timeout và cancellation propagation.
- Đảm bảo message chưa hoàn tất có thể được retry.
- Không chạy background thread vô hạn sau khi invocation kết thúc.
- Dùng durable workflow/queue cho công việc kéo dài hơn invocation budget.

Container platform có thể cung cấp termination grace period hoặc shutdown signal. FaaS provider có lifecycle khác; hãy đọc semantics của platform và không giả định SIGTERM/cleanup hook giống container thông thường.

## 18. Multi-Region và quota

Autoscaling thường chịu quota theo account, project, subscription, Region hoặc service. Một function có thể hoạt động tốt ở Region A nhưng bị throttling ở Region B do quota, capacity pool hoặc dependency khác nhau.

Khi thiết kế multi-Region:

- Kiểm tra concurrency quota và scaling limit ở từng Region.
- Kiểm tra capacity của database/replication và network.
- Tránh chuyển toàn bộ traffic sang Region dự phòng nếu Region đó chưa được kiểm thử ở tải tương ứng.
- Có kế hoạch failover theo từng bước và rate limit.
- Đo cold start, provision rate và dependency latency riêng từng Region.
- Đảm bảo queue, event routing và idempotency chịu được replay cross-Region.

Active-active có thể tăng khả năng sẵn sàng nhưng cũng làm tăng tổng tải và rủi ro xử lý trùng. Active-passive cần capacity dự phòng đủ lớn hoặc chấp nhận ramp-up sau failover. Kiểm thử failover ở tải gần thực tế.

## 19. Quan sát scaling và burst

Autoscaling cần được đánh giá bằng metric ở cả tầng platform, function và dependency.

| Metric | Điều cần biết |
|---|---|
| Concurrent executions/requests | Demand thực tế có đạt giới hạn không? |
| Throttles / 429 / 503 | Request nào bị từ chối và ở tầng nào? |
| Instance count | Bao nhiêu instance đang sẵn sàng? |
| Instance startup/init duration | Mất bao lâu để capacity mới sẵn sàng? |
| Cold start rate | Bao nhiêu request chịu initialization? |
| p95/p99 latency | Burst ảnh hưởng tail latency thế nào? |
| Queue depth/oldest age | Backlog tăng hay giảm? |
| Provisioned capacity utilization | Baseline warm capacity có quá cao/thấp? |
| Database connections | Downstream có bị scale pressure không? |
| Retry/DLQ rate | Throttling có tạo retry storm hoặc poison backlog không? |
| Cost per request/job | Peak capacity có làm chi phí vượt budget? |

Một dashboard nên hiển thị traffic và concurrency trên cùng timeline với instance count, init duration, throttles, queue age và downstream metrics. Chỉ nhìn số instance tăng không chứng minh autoscaling hoạt động tốt; mục tiêu là đáp ứng SLA mà không làm dependency quá tải.

## 20. Load testing cho autoscaling và burst

Load test cần mô phỏng hình dạng traffic, không chỉ gửi một RPS cố định trong vài phút.

Các kịch bản:

1. **Baseline:** tải bình thường để xác định latency và cost nền.
2. **Step load:** nhảy nhanh từ tải thấp lên peak.
3. **Ramp load:** tăng đều theo thời gian để quan sát scale-out.
4. **Spike:** burst rất ngắn rồi giảm nhanh.
5. **Sustained peak:** giữ peak đủ lâu để quan sát ổn định.
6. **Soak:** tải trung bình kéo dài để phát hiện leak, pool exhaustion và chi phí.
7. **Overload:** vượt capacity có chủ đích trong môi trường an toàn để xác nhận backpressure.
8. **Recovery:** giảm tải và đo thời gian backlog/latency trở về bình thường.
9. **Failover:** mất một dependency hoặc Region và quan sát scale/queue behavior.

### Ví dụ traffic profile

~~~text
Phase             Duration      Load
Warm baseline     5 min         50 RPS
Ramp-up           2 min         50 -> 500 RPS
Burst             10 sec        1,500 RPS
Sustained peak     10 min        500 RPS
Cool-down          5 min         500 -> 50 RPS
Recovery           5 min         50 RPS
~~~

Đây là profile minh họa. Điều chỉnh theo traffic thực tế và SLA. Không chạy test gây tải lên production dependency hoặc dịch vụ bên thứ ba khi chưa có phạm vi được phê duyệt.

### Điều cần ghi nhận

- Thời điểm load generator phát request.
- Thời điểm platform bắt đầu scale.
- Thời điểm instance đầu tiên mới sẵn sàng.
- Thời điểm capacity đạt target.
- Tỷ lệ throttling và timeout.
- p50/p95/p99 latency.
- Queue backlog và thời gian drain.
- Database connections và external API rate.
- Tổng chi phí hoặc proxy cost theo invocation/instance.

Load generator cũng có thể trở thành bottleneck. Dùng nhiều generator hoặc phân vùng tải nếu cần, và xác minh chúng có đủ network/CPU để tạo đúng traffic profile.

## 21. Ví dụ kiến trúc điều tiết burst cho Java order service

Giả sử API nhận đơn hàng. Client có thể gửi burst khi chiến dịch bắt đầu. Mỗi request cần validate, ghi nhận order và gọi inventory/payment. Nếu function đồng bộ gọi tất cả dependency, burst có thể tạo nhiều connection và request đồng thời.

Một thiết kế có thể:

1. API gateway xác thực, áp dụng per-client rate limit và validate kích thước request.
2. Java ingress function ghi operation record bền vững và enqueue event.
3. API trả 202 cùng operation ID nếu contract bất đồng bộ.
4. Queue giữ backlog khi traffic đến vượt consumer capacity.
5. Java worker scale theo backlog nhưng bị giới hạn concurrency.
6. Worker dùng idempotency key để xử lý message redelivery.
7. Database proxy/pool và external API rate limit bảo vệ dependency.
8. DLQ lưu message không xử lý được sau retry policy.
9. Workflow cập nhật trạng thái và phát event hoàn tất.
10. Dashboard theo dõi queue age, consumer concurrency, dependency latency và order completion time.

~~~mermaid
flowchart TD
    A[Clients / burst] --> B[API Gateway]
    B --> C[Auth + rate limit]
    C --> D[Java ingress function]
    D --> E[(Operation store)]
    D --> F[Durable queue]
    F --> G[Consumer autoscaling]
    G --> H[Java worker functions]
    H --> I[Idempotency check]
    I --> J[(Database / proxy)]
    I --> K[External API]
    H --> L[DLQ]
    H --> M[Workflow state]
    F --> N[Backlog / age metrics]
    G --> N
    H --> O[Logs / metrics / traces]
~~~

Kiến trúc này tách tốc độ tiếp nhận khỏi tốc độ xử lý, nhưng cần quy định rõ khi nào order được xem là accepted, processing hay completed. Queue enqueue thành công không có nghĩa thanh toán hoặc giữ tồn kho đã thành công.

## 22. Những lỗi thường gặp khi thiết kế autoscaling

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Cho rằng autoscaling tức thì | Burst tạo throttling trước khi capacity sẵn sàng | Đo provisioning lag và thiết kế buffer |
| Nhầm max concurrency với provisioning rate | Capacity target đủ nhưng ramp-up vẫn chậm | Theo dõi concurrency và startup rate riêng |
| Dùng average latency duy nhất | Tail request giữ concurrency lâu hơn dự tính | Đo p95/p99 và workload mix |
| Tăng concurrency vô hạn | Database/API downstream quá tải | Đặt cap theo dependency capacity |
| Scale queue consumer theo depth mà không giới hạn | Retry storm và connection exhaustion | Max concurrency, backoff và DLQ |
| Giữ warm bằng ping liên tục | Chi phí tăng nhưng không bảo đảm reuse environment | Dùng provisioned/min capacity chính thức |
| Scale-in quá nhanh | Instance bị thu hồi khi workload chưa hoàn tất | Graceful shutdown và durable state |
| Dùng queue nhưng trả success cuối cùng | Client hiểu nhầm operation đã hoàn tất | Dùng 202 và operation status |
| Không test burst | Production mới phát hiện cold start/throttle | Step, spike, ramp và failover test |
| Chỉ tăng function capacity khi DB chậm | Tăng áp lực lên bottleneck | Đo dependency và điều tiết concurrency |
| Không tính quota theo Region | Failover Region bị throttling | Kiểm tra và thử tải từng Region |
| Retry ngay khi throttled | Tạo tải lớn hơn và kéo dài outage | Exponential backoff, jitter, retry budget |

## 23. Quy trình thiết kế capacity và scaling policy

Khi chuẩn bị một Java function hoặc service serverless:

1. **Phân loại workload:** HTTP synchronous, async queue, stream hay workflow.
2. **Đo traffic profile:** baseline, peak, burst magnitude, ramp rate và thời lượng peak.
3. **Đo service time:** p50/p95/p99 theo route và dependency.
4. **Ước lượng concurrency:** dùng Little’s Law làm điểm bắt đầu, sau đó benchmark.
5. **Xác định instance capacity:** concurrency hiệu quả mỗi environment/container.
6. **Kiểm tra provisioning:** đo startup latency, scale-out lag và provider quota.
7. **Đặt baseline:** minimum/provisioned capacity nếu SLA yêu cầu.
8. **Đặt giới hạn:** reserved/max concurrency, max instances và API rate limit.
9. **Bảo vệ dependency:** database pool, proxy, external API quotas và circuit breaker.
10. **Chọn buffer:** queue, batching và backlog age SLA cho công việc async.
11. **Thiết kế retry:** backoff, jitter, idempotency, DLQ và retry budget.
12. **Load test:** step, ramp, spike, sustained peak, overload và recovery.
13. **Quan sát:** concurrency, init duration, throttles, p99, queue age, dependency load và cost.
14. **Điều chỉnh:** thay đổi policy từng bước và xác nhận không tạo scale oscillation.

## 24. Checklist production

- **Traffic model:** đã biết baseline, peak, spike, ramp rate và thời lượng peak.
- **Concurrency:** đã ước lượng theo RPS và duration, sau đó xác minh bằng load test.
- **Instance capacity:** đã biết concurrency hiệu quả trên mỗi environment/container.
- **Provisioning rate:** đã đo thời gian scale-out trong đúng Region/account/project.
- **Cold start:** có số liệu init duration riêng; Java bootstrap và dependency initialization đã được tối ưu.
- **Warm capacity:** minimum/provisioned instances được đặt theo SLA và budget.
- **Limits:** account quota, reserved concurrency, max instances và event source limits đã được kiểm tra.
- **Admission control:** gateway/per-tenant rate limit và overload response được cấu hình.
- **Queue:** backlog, oldest message age, consumer max concurrency và DLQ có alarm.
- **Downstream:** database connections, API quotas và connection pool có giới hạn phù hợp.
- **Retry:** backoff, jitter, retry budget và idempotency bảo vệ side effect.
- **Scale-in:** state bền vững, timeout và cleanup không phụ thuộc instance sống lâu.
- **Multi-Region:** từng Region có quota, dependency và failover capacity đã được thử.
- **Observability:** dashboard có instance count, concurrency, throttles, p95/p99, queue age và startup duration.
- **Load test:** đã chạy step, ramp, spike, sustained peak, overload và recovery trong môi trường phù hợp.
- **Cost:** đã tính chi phí warm capacity, peak concurrency, backlog, retry và telemetry.

## 25. Kết luận

Autoscaling giúp serverless điều chỉnh capacity theo nhu cầu, nhưng khả năng chịu burst phụ thuộc đồng thời vào concurrency quota, provisioning rate, startup latency và sức chịu tải của dependency. Concurrency cho biết số invocation/request đang chạy; throughput cho biết tốc độ hoàn tất; instance count cho biết số environment; provisioning rate cho biết capacity mới được cấp nhanh đến đâu.

Với Java function, JVM và dependency initialization có thể làm tăng cold start. Provisioned concurrency hoặc minimum instances giúp duy trì baseline sẵn sàng, nhưng tải vượt baseline vẫn cần scale-out. Queue buffering, rate limiting và concurrency cap giúp hấp thụ hoặc điều tiết burst; chúng cần đi cùng idempotency, retry policy và giám sát backlog.

Hãy dùng Little’s Law để ước lượng concurrency, load test để đo scale-out lag và p95/p99, đồng thời kiểm tra database/API capacity trước khi tăng giới hạn. Mục tiêu là đáp ứng SLA khi tải thay đổi, giữ downstream ổn định và kiểm soát chi phí trong cả giờ bình thường lẫn đợt burst lớn.
