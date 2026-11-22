# Ước lượng concurrency từ lưu lượng và thời gian xử lý

Concurrency là số request, invocation hoặc đơn vị công việc đang được xử lý tại cùng một thời điểm. Trong serverless, nền tảng thường tự tạo thêm execution environment hoặc instance khi tải tăng, nhưng concurrency vẫn có giới hạn từ quota, cấu hình function, nguồn event, database và dịch vụ phụ thuộc. Nếu ước lượng quá thấp, request bị throttle, queue backlog tăng hoặc latency vượt SLO. Nếu đặt giới hạn quá cao, hệ thống có thể tạo một đợt tải lớn lên database và API downstream.

Một cách ước lượng nền tảng là **Little’s Law**: số công việc trung bình đang nằm trong hệ thống bằng tốc độ công việc đi vào nhân với thời gian trung bình một công việc ở trong hệ thống. Với HTTP API, công thức thường được dùng dưới dạng concurrency xấp xỉ request rate nhân thời gian xử lý. Với batch consumer, cần đổi event rate thành invocation rate dựa trên batch size rồi mới tính concurrency.

Bài học trình bày cách đo lưu lượng, thời gian xử lý, peak traffic và headroom; tính concurrency cho HTTP và event-driven function; đối chiếu với giới hạn của nền tảng và khả năng downstream; sau đó kiểm chứng bằng load test và monitoring.

## 1. Concurrency là gì?

Concurrency là số công việc đang được thực hiện đồng thời. Tùy loại workload, đơn vị có thể là:

- HTTP request đang được xử lý.
- Lambda invocation đang chạy.
- Request đồng thời trên một Cloud Run instance.
- Batch message đang được một worker xử lý.
- Stream batch đang được xử lý trên shard.
- Job đang chạy trong một workflow.

Concurrency khác với request rate và throughput:

| Đại lượng | Ý nghĩa | Đơn vị ví dụ |
|---|---|---|
| Arrival rate | Số request/event đến trong một đơn vị thời gian | request/second (RPS), events/second |
| Throughput | Số công việc hoàn tất trong một đơn vị thời gian | completed requests/second |
| Latency/service time | Thời gian một công việc được xử lý hoặc ở trong hệ thống | ms, seconds |
| Concurrency | Số công việc đang xử lý cùng lúc | request, invocation, worker |
| Queue depth | Số công việc đang chờ xử lý | messages, jobs |

Một API có thể nhận 200 request/giây nhưng chỉ có 40 request đang chạy đồng thời nếu mỗi request hoàn tất trung bình trong 200 ms. Ngược lại, 50 request/giây có thể cần 250 concurrency nếu mỗi request mất trung bình 5 giây.

## 2. Little’s Law và công thức cơ bản

Little’s Law mô tả hệ thống ổn định:

```text
L = λ × W
```

Trong đó:

- **L:** số công việc trung bình trong hệ thống.
- **λ (lambda):** tốc độ công việc đi vào/được hoàn tất trong trạng thái ổn định.
- **W:** thời gian trung bình một công việc ở trong hệ thống.

Với request đang được xử lý:

```text
Average concurrency ≈ arrival rate × average service time
```

Ví dụ:

- API nhận trung bình 100 request/giây.
- Thời gian xử lý trung bình là 0,3 giây.

```text
Concurrency ≈ 100 × 0.3 = 30
```

Tức là khoảng 30 request đang chạy đồng thời trong trạng thái ổn định.

### Phải dùng đơn vị nhất quán

Nếu arrival rate là request/giây thì thời gian phải đổi sang giây. Ví dụ 250 ms = 0,25 giây.

```text
80 requests/second × 250 milliseconds
= 80 × 0.25
= 20 concurrent requests
```

Không nhân RPS với thời gian tính bằng mili giây rồi coi kết quả là số concurrency.

### Phân biệt service time và end-to-end time

Với HTTP request, service time cần dùng cho phép tính concurrency là thời gian request chiếm một slot xử lý tại function/service. Nó có thể bao gồm thời gian chờ database hoặc API downstream nếu request vẫn giữ slot trong lúc chờ.

Với queue, thời gian nằm trong hệ thống có thể bao gồm cả thời gian chờ queue và thời gian xử lý. Khi ước lượng số worker đang thực thi, dùng thời gian xử lý của invocation; khi ước lượng tổng số message đang tồn tại trong queue và worker, dùng thời gian từ lúc nhận đến khi hoàn tất.

Little’s Law áp dụng cho hệ thống ổn định. Nếu arrival rate lớn hơn khả năng xử lý trong thời gian dài, backlog sẽ tăng và giả định steady-state không còn đúng.

## 3. Ước lượng concurrency cho HTTP function

Với HTTP function xử lý một request trong mỗi invocation, công thức cơ bản là:

```text
Required concurrency ≈ peak RPS × average request duration
```

Ví dụ:

- Peak traffic: 180 RPS.
- Average duration: 400 ms = 0,4 giây.

```text
Required concurrency ≈ 180 × 0.4 = 72
```

Hệ thống cần khoảng 72 request đồng thời trong giai đoạn peak theo giả định này. Đây là ước lượng tải trung bình ở mức peak, chưa phải giới hạn an toàn cuối cùng.

Nếu function xử lý một request mất 1,5 giây và nhận 200 RPS:

```text
200 × 1.5 = 300 concurrent requests
```

Tăng latency do database chậm có thể làm concurrency tăng ngay cả khi RPS không đổi. Đây là lý do sự cố downstream có thể gây hiệu ứng dây chuyền: request giữ slot lâu hơn, số request in-flight tăng, instance scale-out và database tiếp tục chịu tải cao hơn.

## 4. Dùng peak traffic và headroom

Không nên chỉ sizing theo traffic trung bình trong ngày. Cần đo và ước lượng:

- Peak sustained RPS trong khoảng thời gian đủ dài.
- Burst RPS trong các đợt tăng ngắn.
- Thời gian xử lý trung bình và phân phối latency.
- Mùa vụ, chiến dịch, lịch batch và giờ cao điểm.
- Tăng trưởng dự kiến của người dùng và tenant.
- Retry hoặc traffic replay sau sự cố.

Có thể thêm headroom để chịu biến động:

```text
Target concurrency =
  peak RPS × representative duration × headroom factor
```

Ví dụ headroom factor 1,5 nghĩa là cộng 50% khoảng dự phòng. Hệ số này là lựa chọn vận hành, không phải hằng số bắt buộc. Workload có burst lớn hoặc dữ liệu đo chưa đầy đủ có thể cần headroom khác.

### Ví dụ tính peak

Giả sử:

- Traffic bình thường: 120 RPS.
- Average duration bình thường: 250 ms.
- Peak traffic: 300 RPS.
- Duration ở peak: 800 ms do downstream chậm hơn.
- Headroom: 1,5.

Bình thường:

```text
120 × 0.25 = 30 concurrent requests
```

Ở peak:

```text
300 × 0.8 = 240 concurrent requests
```

Có headroom:

```text
240 × 1.5 = 360 target concurrent requests
```

Ví dụ cho thấy concurrency tăng do cả lưu lượng lẫn thời gian xử lý. Chỉ lấy peak RPS nhân duration trung bình ngày sẽ đánh giá thấp tải.

### Dùng percentile duration thế nào?

Little’s Law dùng thời gian trung bình. p95/p99 hữu ích để kiểm tra tail latency và xây dựng một ước lượng bảo thủ, nhưng không thay thế công thức chính xác. Nhân peak RPS với p95 duration là heuristic để tạo capacity buffer; kết quả không phải concurrency percentile được bảo đảm.

Nên tính baseline bằng average duration, sau đó dùng load test và phân phối latency để xác định headroom. Nếu latency có đuôi rất dài do timeout, cần xử lý nguyên nhân thay vì chỉ tăng concurrency.

## 5. Tính số instance từ concurrency

Với nền tảng cho phép một instance xử lý nhiều request đồng thời, có thể ước lượng số instance:

```text
Required instances ≈ ceil(target concurrency / target concurrency per instance)
```

Ví dụ target concurrency là 360 và cấu hình Cloud Run instance concurrency là 40:

```text
ceil(360 / 40) = 9 instances
```

Đây là ước lượng theo concurrency. Năng lực thực tế mỗi instance còn phụ thuộc CPU, memory, Java thread pool, connection pool, thời gian CPU-bound và dependency. Một instance được đặt concurrency 40 không có nghĩa nó luôn xử lý tốt 40 request nếu ứng dụng chỉ có thể chạy hiệu quả 8 tác vụ CPU-bound cùng lúc.

### Với AWS Lambda

Một execution environment Lambda thông thường xử lý một invocation tại một thời điểm. Vì vậy, số invocation đồng thời gần với số execution environment đang bận. Công thức RPS × duration thường được dùng để ước lượng concurrent executions.

Ví dụ 60 invocation/giây với duration trung bình 2 giây cần khoảng 120 concurrent executions. Kiểm tra function concurrency, reserved concurrency, account quota và các giới hạn của trigger.

### Với Cloud Run

Cloud Run cho phép cấu hình concurrency tối đa trên mỗi instance. Nền tảng có thể gửi nhiều request đồng thời đến cùng instance. Cần chọn concurrency theo khả năng xử lý thực tế của ứng dụng Java, không chỉ chọn giá trị tối đa.

### Với các nền tảng khác

Azure Functions và các nền tảng serverless khác có cơ chế scale controller, worker/instance concurrency và quota riêng. Dùng công thức để ước lượng tải, sau đó ánh xạ sang setting cụ thể của hosting plan và trigger đang dùng.

## 6. Java concurrency: request đồng thời không bằng thread luôn chạy CPU

Một request có thể dành phần lớn thời gian chờ I/O:

- Chờ database query.
- Chờ HTTP API.
- Chờ object storage.
- Chờ message broker.
- Chờ lock hoặc connection pool.

Do đó, concurrency cao không đồng nghĩa CPU luôn cao. Một service có thể xử lý nhiều request đồng thời bằng thread hoặc async I/O, nhưng vẫn bị giới hạn bởi connection pool và downstream quota.

Ngược lại, workload CPU-bound như nén ảnh, mã hóa, tính toán hoặc chuyển đổi PDF có thể bão hòa CPU ở concurrency thấp hơn.

Khi sizing Java service, đo riêng:

- CPU time trên mỗi request.
- Wall-clock duration.
- Thread count và runnable threads.
- Connection pool active/pending.
- GC pause và heap usage.
- Async task queue depth.
- Downstream latency.

Không tăng concurrency để xử lý một bottleneck CPU-bound nếu điều đó chỉ làm nhiều request tranh cùng CPU và kéo dài latency.

## 7. Ước lượng concurrency cho batch consumer

Với event source mapping hoặc queue consumer, một invocation có thể xử lý nhiều message trong một batch. Vì vậy, không dùng event rate nhân duration của một record đơn lẻ nếu handler xử lý theo batch.

Đặt:

- (lambda_e): event arrival rate (events/second).
- (B): số event trung bình trong một batch.
- (T_b): thời gian xử lý một batch (seconds).

Khi batch đầy và ổn định:

```text
Invocation rate ≈ event rate / average batch size
Concurrency ≈ invocation rate × batch duration
```

Hay:

```text
Concurrency ≈ (event rate / batch size) × batch duration
```

Ví dụ:

- 1.000 events/giây.
- Batch size trung bình 100.
- Batch duration 2 giây.

```text
Invocation rate ≈ 1,000 / 100 = 10 invocations/second
Concurrency ≈ 10 × 2 = 20
```

Nếu batch thực tế chỉ có trung bình 60 record do traffic phân tán hoặc batching window ngắn:

```text
Invocation rate ≈ 1,000 / 60 = 16.7 invocations/second
Concurrency ≈ 16.7 × 2 ≈ 34
```

Batch size cấu hình là mức tối đa; batch size thực tế có thể thấp hơn vì thời gian gom batch, payload limit, shard boundary hoặc traffic không đều.

### Throughput trên mỗi invocation

Có thể ước lượng throughput:

```text
Batch throughput ≈ average batch size / batch duration
```

Nếu mỗi batch có 100 record và mất 2 giây, một invocation xử lý khoảng 50 events/giây. Với 20 invocation chạy đồng thời, tổng throughput lý thuyết khoảng 1.000 events/giây, nếu không có bottleneck khác và batch đủ đầy.

Đo throughput thực tế bằng số record hoàn tất, không chỉ số record nhận vào. Retry và partial batch failure có thể làm throughput hữu ích thấp hơn.

## 8. Concurrency cho từng loại event source

Các event source có giới hạn scale khác nhau. Công thức tính tải là điểm bắt đầu; nguồn event có thể giới hạn số invocation song song.

| Nguồn | Yếu tố ảnh hưởng concurrency |
|---|---|
| SQS Standard | Số message sẵn có, số poller, batch size, maximum concurrency và giới hạn function |
| SQS FIFO | Số message group có thể xử lý song song, batch và giới hạn mapping |
| Kinesis Data Streams | Số shard, parallelization factor, batch và ordering theo partition key |
| DynamoDB Streams | Số shard, parallelization factor, batch và ordering theo item |
| Pub/Sub | Số subscriber/instance, flow control, ack deadline và batch settings |
| EventBridge | Quy tắc gọi target, quota và throttling của target/service |
| Scheduled event | Số lịch chạy trùng nhau, thời lượng job và giới hạn concurrency |

### SQS Standard

Standard queue có thể mở rộng nhiều poller và consumer invocation. Maximum concurrency của event source mapping có thể dùng để giới hạn số invocation đồng thời từ mapping. Cần phối hợp giới hạn này với reserved concurrency của function.

Nếu queue có backlog lớn, concurrency có thể tăng nhanh. Hãy kiểm tra khả năng database và API downstream trước khi cho consumer scale tối đa.

### SQS FIFO

FIFO giữ thứ tự trong message group. Các message thuộc cùng một group không thể được xử lý song song tùy ý; số message group đang hoạt động có thể giới hạn concurrency hữu ích. Tăng concurrency mà chỉ có một message group sẽ không tạo ra throughput tuyến tính.

### Kinesis và DynamoDB Streams

Concurrency bị ảnh hưởng bởi số shard và parallelization factor. Với parallelization factor bằng 1, mapping thường xử lý một batch tại một thời điểm trên mỗi shard. Tăng factor có thể tăng số batch đồng thời trong giới hạn dịch vụ, nhưng cần giữ ordering theo partition key/item và bảo đảm downstream chịu được tải.

Đừng lấy số shard nhân batch size để suy ra invocation concurrency. Batch size là số record mỗi invocation; shard/parallelization quyết định số batch có thể chạy song song.

## 9. Giới hạn concurrency của nền tảng

Sau khi tính target concurrency, cần đối chiếu các lớp giới hạn:

1. **Account/service quota:** tổng concurrency hoặc số instance được phép trong account/project/region.
2. **Function reserved/max concurrency:** giới hạn riêng cho function hoặc workload.
3. **Provisioned/warm capacity:** số execution environment/instance được chuẩn bị trước để giảm cold start; không đồng nghĩa giới hạn tổng concurrency.
4. **Trigger limit:** số poller, shard, message group hoặc maximum concurrency của event source.
5. **Instance concurrency:** số request một instance nhận cùng lúc.
6. **Downstream capacity:** database, API, cache và connection pool.
7. **Network capacity:** NAT, egress, connection tracking hoặc giới hạn socket.

Nếu target concurrency là 360 nhưng function chỉ được phép chạy 200 invocation đồng thời, phần tải vượt giới hạn có thể bị throttle hoặc chờ tùy nền tảng và trigger. Cần quyết định có tăng quota, giảm peak, queue/buffer hay giới hạn admission.

### Reserved concurrency và provisioned concurrency

Trên AWS Lambda:

- **Reserved concurrency** dành riêng một phần concurrency cho function và đặt giới hạn trên cho function đó.
- **Provisioned concurrency** chuẩn bị trước execution environments để giảm cold start cho một lượng invocation nhất định.

Provisioned concurrency không tự động cho phép function vượt account quota hoặc reserved concurrency. Nếu traffic vượt capacity đã chuẩn bị, Lambda có thể cần scale thêm execution environment và có thể xuất hiện cold start theo cấu hình/quota.

Trên Cloud Run, minimum instances giúp duy trì instance ấm; maximum instances giới hạn scale-out; concurrency setting xác định số request tối đa mỗi instance. Ba setting này giải quyết các vấn đề khác nhau.

## 10. Database thường là giới hạn trước function

Serverless có thể scale invocation rất nhanh, nhưng database thường có giới hạn connection, CPU, IOPS hoặc transaction throughput.

Ví dụ:

- Maximum instances: 20.
- Connection pool tối đa mỗi instance: 10.
- Tổng connection tiềm năng: 20 × 10 = 200.

Nếu database chỉ chịu được 80 connection cho ứng dụng này, cấu hình có thể gây cạn connection dù function scale đúng theo traffic.

```text
Potential database connections
≈ active instances × pool max per instance
```

Cần tính thêm connection của admin tool, migration, worker khác và service khác. Đặt pool size theo ngân sách tổng, dùng connection proxy/pooling phù hợp và giới hạn max instances nếu cần.

### Một request không nhất thiết giữ một connection suốt đời

Connection pool thường chỉ giữ connection trong lúc truy vấn. Tuy nhiên, nếu mỗi request mở transaction lâu hoặc giữ connection khi chờ API bên ngoài, số connection cần có thể tăng mạnh.

Không giữ transaction mở trong khi gọi payment provider hoặc xử lý tác vụ dài nếu không cần. Giữ transaction ngắn giúp giảm lock time và connection occupancy.

## 11. Fan-out làm tăng concurrency downstream

Một request có thể gọi nhiều dịch vụ. Nếu mỗi request tạo 3 lời gọi đồng thời đến inventory, pricing và customer service, downstream có thể nhận nhiều request hơn concurrency của API.

Ví dụ:

- API concurrency: 200.
- Mỗi request tạo 3 downstream calls song song.
- Tổng downstream in-flight calls xấp xỉ 600 nếu tất cả cùng hoạt động.

```text
Downstream in-flight concurrency
≈ incoming request concurrency × concurrent calls per request
```

Nếu các call được thực hiện tuần tự, số call đồng thời có thể thấp hơn, nhưng tổng request rate đến dependency vẫn tăng theo số lần gọi trên mỗi operation.

Hãy xác định fan-out factor, retry factor và timeout. Retry ở nhiều lớp có thể nhân số request. Ví dụ API retry worker, worker retry provider và provider client retry có thể tạo amplification lớn khi dependency chậm.

## 12. Headroom, utilization và giới hạn an toàn

Target concurrency không nên bằng đúng maximum capacity. Khi hệ thống hoạt động sát 100% khả năng, hàng đợi và latency thường tăng nhanh do biến động thời gian xử lý.

Một cách quản lý là đặt target utilization cho resource quan trọng:

```text
Required capacity ≈ expected load / target utilization
```

Ví dụ nếu tải CPU dự kiến cần 6 vCPU ở mức 100%, và muốn giữ utilization mục tiêu 70%:

```text
Required CPU capacity ≈ 6 / 0.70 ≈ 8.6 vCPU
```

Đây là cách ước lượng capacity cho CPU, không phải công thức thay thế Little’s Law. Với concurrency, dùng arrival rate × duration rồi thêm headroom; với CPU, dùng throughput benchmark và utilization mục tiêu.

Headroom cần cân bằng:

- Tải tăng đột ngột.
- Cold start và thời gian scale-out.
- Request duration biến động.
- Retry và replay sau sự cố.
- Một instance hoặc zone mất khả năng phục vụ.
- Quota và khả năng mở rộng của downstream.

## 13. Backpressure và admission control

Nếu arrival rate vượt khả năng xử lý, tăng concurrency không phải lúc nào cũng đúng. Hệ thống cần điều tiết đầu vào để tránh làm sụp đổ dependency.

Các biện pháp:

- Đưa công việc vào queue bền vững thay vì xử lý đồng bộ.
- Giới hạn maximum concurrency của consumer.
- Áp dụng rate limit theo client hoặc tenant.
- Trả 429/503 có Retry-After phù hợp khi không thể nhận thêm.
- Dùng bounded queue và từ chối sớm khi đầy.
- Giới hạn số downstream calls đồng thời bằng semaphore/bulkhead.
- Dùng circuit breaker để ngừng gọi dependency đang lỗi.
- Tách workload interactive và batch để tránh tranh tài nguyên.
- Có deadline end-to-end và timeout cho từng chặng.

Backpressure giúp bảo vệ hệ thống bằng cách làm chậm hoặc từ chối tải khi cần. Nếu client retry ngay lập tức mà không có backoff/jitter, backpressure có thể biến thành retry storm.

### Queue là bộ đệm, không phải năng lực vô hạn

Queue hấp thụ burst ngắn, nhưng nếu average arrival rate lâu dài lớn hơn average processing rate, backlog vẫn tăng. Cần theo dõi age, depth, retention và thời gian để drain backlog.

### Ước lượng throughput tối đa và thời gian drain

Nếu biết concurrency cap và thời gian xử lý đại diện, có thể ước lượng throughput tối đa lý thuyết:

~~~text
Theoretical throughput ≈ concurrency cap / average service time
~~~

Ví dụ cap 200 request đồng thời và service time trung bình 0,8 giây cho throughput lý thuyết khoảng 250 request/giây. Đây là giới hạn theo mô hình đơn giản; CPU, downstream, quota và biến động latency thường làm throughput bền vững thấp hơn. Hãy dùng benchmark để tìm sustainable throughput rồi đặt admission limit thấp hơn mức bão hòa.

Với queue, nếu backlog hiện tại là Q, processing capacity là μ events/second và arrival rate tiếp tục là λ events/second, thời gian drain gần đúng khi μ > λ là:

~~~text
Drain time ≈ Q / (μ - λ)
~~~

Ví dụ backlog 120.000 event, consumer có thể xử lý 1.500 event/giây và producer vẫn gửi 1.000 event/giây:

~~~text
Drain time ≈ 120,000 / (1,500 - 1,000) = 240 seconds
~~~

Nếu μ ≤ λ, backlog không giảm trong khi traffic tiếp tục đến. Khi đó cần tăng processing capacity, giảm arrival rate, tạm dừng producer hoặc áp dụng admission control. Công thức drain chỉ là ước lượng khi throughput tương đối ổn định và không có giới hạn retention, partition hoặc dependency thay đổi.

## 14. Cold start và tốc độ scale-out

Khi traffic tăng, nền tảng cần tạo execution environment hoặc instance mới. Java runtime có thể cần thời gian cho JVM startup, class loading, framework initialization, dependency injection và connection setup.

Concurrency target phải tính đến khả năng nền tảng scale đủ nhanh. Nếu burst tăng từ 20 lên 500 request trong vài giây, công thức cho biết capacity cần thiết nhưng không bảo đảm capacity xuất hiện tức thời.

Biện pháp:

- Provisioned concurrency hoặc minimum instances cho workload nhạy latency.
- Tối ưu startup và dependency graph của Java.
- Đặt min/max instances hợp lý.
- Dùng queue để hấp thụ burst cho workload async.
- Giới hạn admission để tránh quá tải trong lúc scale.
- Theo dõi cold start và time-to-scale trong load test.

Không bật provisioned capacity cho mọi function theo mặc định. So sánh chi phí giữ instance ấm với giá trị giảm latency và yêu cầu SLO.

## 15. Ví dụ Java tính concurrency sơ bộ

Có thể viết helper nhỏ để tránh nhầm đơn vị và làm rõ headroom. Đây chỉ là phép tính ban đầu; số liệu đầu vào cần đến từ production metrics hoặc load test.

~~~java
public record ConcurrencyEstimate(
        double peakRequestsPerSecond,
        double averageDurationMillis,
        double headroomFactor) {

    public ConcurrencyEstimate {
        if (!Double.isFinite(peakRequestsPerSecond)
                || !Double.isFinite(averageDurationMillis)
                || !Double.isFinite(headroomFactor)
                || peakRequestsPerSecond <= 0
                || averageDurationMillis <= 0
                || headroomFactor < 1.0) {
            throw new IllegalArgumentException(
                    "Invalid concurrency estimate inputs");
        }
    }

    public long requiredConcurrency() {
        double durationSeconds = averageDurationMillis / 1_000.0;
        double rawConcurrency =
                peakRequestsPerSecond * durationSeconds;
        return (long) Math.ceil(rawConcurrency * headroomFactor);
    }

    public static void main(String[] args) {
        var estimate = new ConcurrencyEstimate(
                300,   // peak RPS
                800,   // average duration at peak, milliseconds
                1.5);  // 50% headroom

        System.out.println(
                "Target concurrency = "
                        + estimate.requiredConcurrency());
    }
}
~~~

Kết quả ví dụ là 360. Helper không tính được quota, database capacity, batch source limit hoặc cold start; các phần đó cần được đánh giá riêng.

## 16. Load test để xác minh sizing

Công thức cho baseline. Load test xác nhận ứng dụng, runtime và dependency hoạt động thế nào dưới tải thật.

Một kế hoạch kiểm thử nên có:

| Kiểu test | Mục đích |
|---|---|
| Baseline | Đo latency và throughput ở tải thông thường |
| Ramp-up | Tăng dần RPS để xác định điểm bắt đầu scale |
| Peak sustained | Giữ peak traffic đủ lâu để kiểm tra steady state |
| Spike | Tăng tải nhanh để quan sát scale-out và throttling |
| Soak | Chạy lâu để phát hiện leak, pool exhaustion và memory growth |
| Cold-start test | Tạo instance mới và đo request đầu tiên |
| Dependency degradation | Làm chậm database/API trong môi trường test để xem concurrency tăng thế nào |
| Recovery/replay | Đưa backlog hoặc retry vào để xác định khả năng drain |

Đo ít nhất:

- Arrival rate thực tế và completed throughput.
- Active concurrency theo function/instance.
- Duration p50/p95/p99.
- Queue depth và age.
- Throttle, timeout, retry và error rate.
- CPU, memory, GC và thread pool.
- Database active/pending connections.
- Downstream in-flight requests và latency.
- Cold start count và scale-out delay.

Dùng workload có phân bố payload và dependency tương tự production. Một test chỉ gọi handler rỗng không phản ánh concurrency khi function truy cập database và API bên ngoài.

### Open-loop và closed-loop load test

Closed-loop client chờ response rồi mới gửi request tiếp theo. Khi server chậm, client tự giảm tốc độ gửi, có thể che mất khả năng hệ thống bị quá tải.

Open-loop test phát request theo arrival rate định trước, phù hợp để kiểm tra hệ thống chịu được peak RPS nào. Cần giới hạn tải và chạy trong môi trường được phép để không gây ảnh hưởng production.

## 17. Monitoring sau triển khai

Theo dõi cả concurrency và các dấu hiệu cho thấy hệ thống sắp chạm giới hạn.

| Metric | Ý nghĩa |
|---|---|
| Concurrent executions/requests | Số invocation hoặc request đang chạy |
| Throttles/rejected requests | Tải bị từ chối do giới hạn |
| Duration p50/p95/p99 | Thời gian xử lý và tail latency |
| Instance count | Mức scale-out hiện tại |
| Pending requests | Request chờ instance hoặc capacity |
| Queue depth/age | Backlog và thời gian chờ |
| Iterator age | Độ trễ đọc stream |
| Retry/DLQ count | Lỗi xử lý và công việc bị chuyển cách ly |
| DB active/pending connections | Áp lực connection pool |
| Downstream latency/error | Tình trạng dependency |
| CPU/memory/GC | Giới hạn tài nguyên của Java runtime |
| Cold start/startup latency | Chi phí khởi tạo instance mới |

Đặt cảnh báo cho các tín hiệu kết hợp. Ví dụ, concurrency gần max cùng với throttle tăng là dấu hiệu capacity không đủ; concurrency tăng cùng DB connection wait là dấu hiệu downstream đang là bottleneck. Queue age tăng trong khi consumer concurrency đã chạm max cho thấy cần tăng processing capacity hoặc giảm arrival rate.

Không chỉ cảnh báo khi concurrency đạt 100%. Nếu latency và error rate đã tăng ở mức 70%, cần điều tra trước khi chạm giới hạn.

## 18. Những lỗi sizing thường gặp

- **Dùng average RPS cả ngày:** bỏ qua peak và burst; tính theo peak sustained và kiểm tra spike.
- **Quên đổi milliseconds sang seconds:** làm kết quả sai 1.000 lần.
- **Dùng p99 như average mà không giải thích:** tạo ước lượng khó diễn giải; dùng average cho Little’s Law và percentile để đánh giá tail/headroom.
- **Chỉ tính function concurrency:** bỏ qua database, API và queue downstream.
- **Cho rằng max concurrency càng cao càng tốt:** có thể làm cạn connection hoặc quota dependency.
- **Dùng batch size cấu hình thay cho batch size thực tế:** invocation rate bị đánh giá thấp.
- **Bỏ qua shard hoặc message group:** event source không thể scale vượt giới hạn song song của nguồn.
- **Không tính retry amplification:** sự cố dependency làm số outbound request tăng nhiều lần.
- **Coi provisioned concurrency là max concurrency:** đây là hai mục đích khác nhau.
- **Không đo cold start và scale-out delay:** burst có thể vượt SLO trước khi instance mới sẵn sàng.
- **Không có backpressure:** backlog và latency tăng không kiểm soát.
- **Chỉ test function rỗng:** không phát hiện database pool và downstream bottleneck.
- **Không theo dõi queue age:** backlog có thể tăng dù invocation vẫn thành công.
- **Không dành headroom:** hệ thống hoạt động sát giới hạn và dễ bị ảnh hưởng bởi biến động nhỏ.

## 19. Quy trình ước lượng concurrency

Khi sizing một Java serverless workload, thực hiện theo thứ tự:

1. Xác định đơn vị công việc: HTTP request, invocation, batch hay business operation.
2. Đo arrival rate theo giây và phân bố peak/burst.
3. Đo thời gian xử lý trung bình ở tải đại diện; theo dõi p95/p99.
4. Dùng Little’s Law để tính concurrency baseline.
5. Với batch, đổi event rate sang invocation rate bằng batch size thực tế rồi nhân batch duration.
6. Thêm headroom dựa trên biến động và tốc độ scale-out.
7. Đối chiếu account quota, function limit, trigger limit và instance concurrency.
8. Tính downstream concurrency, database connections và fan-out.
9. Đặt max concurrency, rate limit và backpressure theo ngân sách dependency.
10. Chọn min/provisioned capacity nếu cold start ảnh hưởng SLO.
11. Load test ramp, peak, spike, soak và dependency degradation.
12. Theo dõi concurrency, throttle, latency, queue age và downstream saturation sau deploy.
13. Điều chỉnh bằng dữ liệu production thay vì giữ nguyên giả định ban đầu.

## 20. Ghi nhớ

Little’s Law cho phép ước lượng concurrency trung bình bằng arrival rate nhân thời gian một công việc ở trong hệ thống. Với HTTP function, dùng peak RPS và request duration; với batch consumer, tính invocation rate từ event rate và batch size thực tế rồi nhân batch duration.

Kết quả chỉ là baseline. Cần thêm headroom, đối chiếu giới hạn của function và event source, kiểm tra khả năng database/API downstream, rồi xác minh bằng load test. Concurrency quá thấp gây throttle và backlog; concurrency quá cao có thể làm quá tải dependency hoặc tăng chi phí.

Trong Java serverless, đo wall-clock duration cùng CPU, thread, connection pool và cold start. Đặt giới hạn và backpressure theo năng lực của toàn bộ hành trình, không chỉ theo khả năng scale của function. Sau triển khai, dùng metric concurrency, latency, queue age và downstream saturation để cập nhật sizing theo tải thực tế.

