# Kiểm thử tải kéo dài, tải đột biến và hành vi khi quá tải trong Spring AMQP

## 1. Vấn đề cần giải quyết: nhanh ở tải thấp chưa đủ

Trong **SPRING_AMQP**, `RabbitTemplate` gửi message tới exchange; queue, binding và routing key xác định đường đi; `@RabbitListener` nhận và xử lý, thường kết hợp publisher confirms, acknowledgements, retry, dead-letter (DLX/DLQ) và transaction. Hệ thống có thể hoạt động tốt khi chỉ có 20 message/giây nhưng bị nghẽn khi một chiến dịch tạo 2.000 message/giây hoặc khi cơ sở dữ liệu đột ngột chậm hơn.

Kiểm thử hiệu năng cho hệ thống message không chỉ là đo “publish được bao nhiêu message/giây”. Cần trả lời đồng thời:

1. **Tải kéo dài (sustained/steady load):** hệ thống có giữ thông lượng ổn định trong hàng chục phút hoặc hàng giờ mà backlog, memory và latency không tăng vô hạn?
2. **Tải đột biến (burst/spike):** khi tốc độ đầu vào tăng gấp nhiều lần trong thời gian ngắn, message có được giữ an toàn và hệ thống hồi phục về trạng thái bình thường sau bao lâu?
3. **Quá tải (overload):** khi ingress vượt năng lực xử lý hoặc RabbitMQ gặp memory/disk alarm, producer và consumer phản ứng như thế nào? Có tự giới hạn in-flight, fail fast, retry có kiểm soát và quan sát được unknown publish outcome không?
4. **Độ tin cậy:** có mất message, xử lý trùng gây side effect, retry nóng, DLQ tăng hay vi phạm thời gian xử lý cam kết không?

**Mục tiêu bài học:** thiết kế profile tải, chạy RabbitMQ PerfTest và workload đi qua Spring AMQP, đo throughput/latency/queue depth/publisher confirms, kiểm thử flow control/resource alarm, xác định giới hạn công suất và xây quy tắc chấp nhận kết quả.

> **Nguyên tắc:** Một hệ thống đạt tốc độ cao bằng cách tắt publisher confirms, sử dụng auto-ack hoặc bỏ qua DB transaction **không được coi là đạt mục tiêu độ tin cậy** của kiến trúc ban đầu. So sánh các phép thử phải giữ nguyên các bảo đảm delivery quan trọng.

## 2. Ba loại tải không thể thay thế cho nhau

| Loại thử nghiệm | Mô hình tải | Phát hiện điều gì? | Chỉ số cần quan sát |
| --- | --- | --- | --- |
| **Sustained / steady** | Ingress ổn định trong 30–120 phút hoặc lâu hơn. | Công suất bền vững, backlog có tăng âm thầm, bottleneck lâu dài. | Confirm rate, ack rate, p95/p99 latency, ready/unacked, CPU, memory, disk. |
| **Soak / endurance** | Tải gần thực tế liên tục nhiều giờ. | Leak connection/channel, tăng heap, disk/metrics cardinality, throughput suy giảm dần. | Resource trend theo giờ, GC, consumer restart, alarms, queue growth. |
| **Burst / spike** | Tốc độ tăng rất nhanh rồi trở về baseline. | Khả năng hấp thụ đỉnh, đỉnh ready/unacked, thời gian drain và tail latency. | Peak depth, confirm latency, p99 end-to-end, recovery time. |
| **Overload / stress** | Tăng tải đến khi vượt năng lực hoặc chủ động làm downstream chậm. | Backpressure, khả năng từ chối tải, resource alarms, retry storm, tính ổn định khi saturation. | Publish failures/timeouts, blocked/flow connections, DLQ, dropped/unknown outcomes. |
| **Recovery after overload** | Giảm tải hoặc khôi phục broker/DB sau giai đoạn nghẽn. | Hệ thống có tự hồi phục, drain backlog và không tạo duplicate side effect không? | Backlog slope, drain time, redelivery, idempotency, error rate. |

### Các hình dạng tải

```mermaid
flowchart LR
    A["Warm-up"] --> B["Steady 500/s"]
    B --> C["Burst 2.000/s"]
    C --> D["Trở lại 500/s"]
    D --> E["Đo drain & recovery"]
```

Đường cong trên là ví dụ để hiểu trình tự. Trong báo cáo thực tế phải lưu **tốc độ thực đạt được**: rate được cấu hình không đồng nghĩa broker đã nhận đủ lượng đó nếu publisher bị chặn hoặc gặp lỗi.

## 3. Mô hình công suất và backlog

Đặt:

- `λ` (lambda): số message thực sự **vào queue mỗi giây**.
- `μ` (mu): số message được consumer **hoàn tất/ack mỗi giây**.
- `B`: queue depth, tức `messages_ready + messages_unacknowledged` đối với classic/quorum queue.
- `W`: thời gian từ khi message vào queue đến khi hoàn tất, bao gồm thời gian chờ và xử lý.

Khi tải có giả định đơn giản **không requeue, TTL, DLX, purge, drop hoặc no-ack**, backlog thay đổi xấp xỉ:

\[
\frac{\Delta B}{\Delta t}\approx \lambda-\mu.
\]

Đây là mô hình để diễn giải kết quả, không phải định luật đầy đủ cho hệ thống có redelivery và nhiều queue retry.

### 3.1. Ví dụ burst rồi drain

Giả sử baseline:

```text
Ingress  = 300 message/giây
Ack      = 500 message/giây (năng lực khi đủ message)

Trong 180 giây burst:
Ingress  = 900 message/giây
Ack      = 500 message/giây

Backlog tích lũy xấp xỉ:
(900 - 500) x 180 = 72.000 message
```

Sau burst, ingress trở về `300/s`, năng lực ack vẫn `500/s`; tốc độ giảm backlog ròng khoảng `200/s`, nên cần xấp xỉ `72.000 / 200 = 360 giây` để trở về trạng thái trước burst. Nếu DB chậm khiến `μ` giảm thì thời gian còn dài hơn.

**Hai phép đo khác nhau:** “burst kéo dài 3 phút” và “hệ thống trở về độ trễ bình thường sau 6 phút” đều ảnh hưởng trải nghiệm người dùng. Một dashboard chỉ hiển thị publish rate sẽ bỏ qua nửa sau.

### 3.2. Little's Law và cách tránh dùng sai

Trong trạng thái **ổn định**, với lưu lượng hiệu dụng và trung bình trên khoảng đủ dài:

\[
L = \lambda W
\]

Trong đó `L` là số message trung bình đang ở trong hệ thống/đoạn pipeline xác định, `λ` là throughput hiệu dụng qua đoạn đó và `W` là thời gian lưu trung bình trong **cùng phạm vi đo**. Công thức **không** cho phép lấy một snapshot `ready` tại thời điểm burst rồi tính chính xác p99 latency bằng `L/λ`. Khi queue tăng liên tục, giả định cân bằng của steady state đã không còn.

### 3.3. Rate được yêu cầu và rate thực tế

Đặt `targetRate=1000/s` trong load generator chỉ là yêu cầu. Để tính ingress/throughput thực, cần tách:

| Tốc độ | Nguồn đo | Ý nghĩa |
| --- | --- | --- |
| Offered rate | Load generator | Số lần tạo yêu cầu publish dự kiến. |
| Attempted publish rate | Ứng dụng | Số lần gọi `RabbitTemplate` thực tế. |
| Confirmed publish rate | Publisher confirms (ack/nack/unknown) | Broker xác nhận publish như thế nào. |
| Queue ingress rate | RabbitMQ per-queue stats | Message thực được route vào queue này. |
| Delivered rate | RabbitMQ consumer stats | Lượt giao (có thể gồm redelivery). |
| Acknowledged rate | Broker consumer ack stats | Lượt delivery được xác nhận. |
| Business completed rate | Ứng dụng/DB | Số event được áp dụng nghiệp vụ thành công, **không đếm trùng**. |

Một publish có thể route tới **nhiều queue** hoặc **không queue nào**. Publisher confirm cũng không có nghĩa consumer đã hoàn tất; bật publisher returns với `mandatory=true` để phân biệt unroutable trong các tình huống cần thiết.

## 4. Chốt điều kiện thử nghiệm trước khi chạy

Tải trên RabbitMQ phụ thuộc rất mạnh vào topology và độ bền:

| Tham số | Phải ghi lại |
| --- | --- |
| Broker | RabbitMQ version, số node, CPU/RAM/disk, container/VM/host, cluster topology. |
| Queue | Classic hay quorum, số queue, leader placement, replication, durable, DLX, TTL, max-length. |
| Message | Kích thước p50/p95, JSON/Avro/binary, persistent delivery mode, số header. |
| Publisher | Số connection/channel, publisher confirms, max in-flight, mandatory/returns, retry/outbox. |
| Consumer | Số instance, `concurrency`, `prefetch`, ack mode, batch size, DB/HTTP processing time. |
| Workload | Arrival rate, burst duration, event key distribution, hot-key, poison ratio, duplicate ratio. |
| Môi trường | TLS, network RTT, CPU quota, cgroup memory, volume IOPS, disk watermark, monitoring scrape. |

**Không so sánh hai bài test khác nhau về persistence và replication như thể chúng chỉ khác concurrency.** Quorum queue với replication và persistent messages có chi phí khác classic queue; bật confirms có thể làm throughput đổi đáng kể so với “fire-and-forget”.

### 4.1. Dữ liệu giống production nhưng không chứa dữ liệu thật

Tạo event tổng hợp có:

- `eventId` duy nhất, `orderId` được phân phối theo tỷ lệ hot/cold key giống thực tế.
- Payload có kích thước đại diện (ví dụ 1 KiB, 10 KiB và một tỷ lệ lớn hơn nếu production có).
- Timestamp do load generator ghi để đo độ trễ; đồng bộ đồng hồ khi đo giữa máy.
- Một tỷ lệ event cố ý lỗi để quan sát retry/DLQ **trong test riêng**, không trộn vào baseline khi chưa có số đo rõ ràng.

Không dùng dữ liệu khách hàng thật, token, credentials hoặc message mang PII trong phép thử chia sẻ kết quả cho nhiều người.

### 4.2. Cô lập môi trường

Khuyến nghị dùng **staging có topology/tài nguyên đại diện**, tách vhost, credentials, queue names và database test khỏi production. Đừng chủ động kích hoạt memory/disk alarm hoặc stop broker trên cluster phục vụ người dùng. Nếu chỉ có laptop Docker, kết quả phù hợp để so sánh **cấu hình trên cùng laptop**, không phải chứng nhận throughput production.

## 5. Chạy baseline bằng RabbitMQ PerfTest

[RabbitMQ PerfTest](https://perftest.rabbitmq.com/) là công cụ đo throughput và latency cho **AMQP 0-9-1**. Nó giúp tách bottleneck của broker khỏi chi phí deserialize JSON, transaction và business code của Spring. Với Streams protocol, phải dùng công cụ Stream PerfTest phù hợp.

Kiểm tra phiên bản trước khi chạy:

```bash
java -jar perf-test.jar --help
```

Các lệnh dưới dùng cú pháp công khai của PerfTest, với:

- `-x`: số publisher; `-y`: số consumer.
- `-u`: tên queue do PerfTest tạo/dùng; không nên dùng queue nghiệp vụ thật.
- `-s`: kích thước message bằng byte.
- `-f persistent`: gửi persistent message.
- `-q`: consumer prefetch.
- `-c`: tối đa số publish outstanding đang chờ confirm.
- `--rate`: giới hạn publish rate; `--variable-rate`: thay đổi rate theo thời gian.
- `-z`: thời lượng phép thử, tính bằng giây.

### 5.1. Baseline 10 phút có publisher confirms

```bash
java -jar perf-test.jar \
  --uri amqp://load-user:load-pass@rabbitmq-staging:5672/%2Fload \
  -x 1 -y 2 -u perf.steady.q \
  -f persistent -s 1024 -q 100 -c 200 \
  --rate 500 -z 600 --id steady-500
```

URI có user/password **chỉ minh họa**: trong môi trường thật không đưa secret vào shell history hoặc CI logs; sử dụng cách truyền URI/credential bảo mật do tổ chức phê duyệt. Vhost `/load` được URL-encode thành `%2Fload`. Nếu chưa có vhost/user hoặc permission configure, PerfTest có thể không tạo được queue; hãy provision trước hoặc cấp quyền đúng cho môi trường kiểm thử.

Phép thử có `1` publisher, `2` consumer, message `1024 byte`, persistent mode, xác nhận publisher với tối đa `200` outstanding, prefetch `100` và offered rate khoảng `500/s` trong `600 giây`. Lưu file output, dashboard và phiên bản tool để tái hiện.

**Quan trọng:** PerfTest consumer và ứng dụng Spring nghiệp vụ là hai workload khác nhau. Nếu PerfTest nhanh hơn đáng kể app thật, bottleneck có thể nằm ở JSON conversion, DB, external API, thread pool hoặc transaction chứ không phải RabbitMQ.

### 5.2. Đo gần giới hạn broker một cách có kiểm soát

Đừng mở nhiều publisher không giới hạn rồi nhìn số publish/s lớn nhất. Hãy chạy lần lượt `250 → 500 → 750 → 1000/s` cùng cấu hình, mỗi mức có warm-up, steady window và cooldown. Tại mỗi mức phải quan sát **ack rate, backlog, p99, memory/disk và confirm latency**. Điểm bền vững là mức tải mà hệ thống còn đáp ứng SLO, chứ không chỉ là đỉnh tốc độ được in ra.

## 6. Kiểm thử tải kéo dài (sustained và soak)

### 6.1. Quy trình 5 giai đoạn

1. **Warm-up**: cho JVM JIT, connection/channel cache, DB connection pool và metrics đạt trạng thái bình thường; không tính warm-up vào kết quả chính.
2. **Đo baseline**: tải thấp, xác nhận metric collection hoạt động và không có lỗi route/ack bất ngờ.
3. **Steady run**: giữ tải mục tiêu liên tục trong khoảng đã chọn (ví dụ 30–120 phút).
4. **Soak run**: chạy thêm nhiều giờ ở tải gần mức sử dụng thật để phát hiện leak và drift.
5. **Cooldown/drain**: giảm/dừng producer, tiếp tục đo đến khi backlog về vùng bình thường; xác minh không có DLQ bất thường hoặc duplicate side effect.

Mẫu PerfTest steady dài hơn (thời lượng minh họa 60 phút):

```bash
java -jar perf-test.jar \
  --uri amqp://rabbitmq-staging:5672 \
  -x 1 -y 2 -u perf.soak.q \
  -f persistent -s 1024 -q 100 -c 200 \
  --rate 500 -z 3600 --id soak-1h
```

Đừng đánh đồng chạy `3600 giây` với một bài soak production hoàn chỉnh. Nhiều leak hoặc disk growth chỉ lộ sau **6–24 giờ**, tùy workload; chọn thời gian theo chi phí và rủi ro hệ thống.

### 6.2. Đọc kết quả sustained

Một phép thử đạt yêu cầu ở `500/s` thường cần chứng minh **đồng thời**:

- Confirmed ingress/queue ingress phù hợp với offered load, không có publish outcome không rõ bị giấu.
- Ack/business completed rate sau warm-up **xấp xỉ mức ingress** (nếu queue đã cân bằng).
- Ready/unacked **không tăng không giới hạn**; có thể dao động theo prefetch và batch.
- p95/p99 end-to-end latency không trôi lên liên tục.
- CPU, GC, RSS/heap, channel/connection count, disk use/IOPS không có xu hướng leak.
- Retry/requeue, nack, DLQ và duplicate **nằm trong ngưỡng đã định**; không dùng DLQ để “giảm backlog” giả tạo.

Một hệ thống có `publisher ack/s≈500` nhưng `consumer ack/s≈300` **không ổn định ở tải này**, dù producer không báo lỗi.

### 6.3. Soak và xu hướng tài nguyên

Theo dõi các triệu chứng dễ bị bỏ sót trong phép test 2 phút:

| Xu hướng theo giờ | Giả thuyết điều tra |
| --- | --- |
| Channel count tăng liên tục | Channel không được trả lại cache/đóng đúng cách hoặc consumer được tạo lặp. |
| Memory application tăng, GC pause dài | Payload buffer, unbounded queue, metrics high-cardinality hoặc retry task leak. |
| Disk broker tăng dù queue ready về 0 | Retention/log, compaction, quorum storage, audit/tracing hoặc snapshot. |
| Connection reconnect nhiều lần | Heartbeat, network, load balancer, TCP/resource exhaustion. |
| p99 tăng trong khi average ổn định | Tail latency do DB lock, GC, disk flush, saturation ở một partition/queue. |
| DLQ từ 0 tăng chậm | Một tỷ lệ nhỏ poison message hoặc failure sau nhiều lần retry. |

**So sánh tốc độ tăng**, không chỉ nhìn giá trị cuối. Với hệ thống có retention theo thiết kế, disk tăng có thể hợp lệ; cần phân biệt “dữ liệu được giữ có chủ đích” với leak.

## 7. Kiểm thử burst/spike và thời gian drain

PerfTest hỗ trợ `--variable-rate RATE:DURATION`, trong đó rate là message/s và duration tính bằng giây. Ví dụ:

```bash
java -jar perf-test.jar \
  --uri amqp://rabbitmq-staging:5672 \
  -x 1 -y 2 -u perf.burst.q \
  -f persistent -s 1024 -q 100 -c 200 \
  --variable-rate 200:120 \
  --variable-rate 1800:30 \
  --variable-rate 200:240 \
  -z 390 --id burst-1800
```

Diễn giải:

1. `120 giây` tải nền `200/s`.
2. `30 giây` spike `1800/s`.
3. `240 giây` quay về `200/s` để xem queue có tự drain hay không.

Không mặc định rằng load generator **đạt đủ 1800/s**: đo attempted/confirmed rate, blocked/flow state và khả năng máy phát tải. Với `-z 390`, kết thúc test có thể còn backlog; để đo **drain hoàn chỉnh**, có thể chạy thêm pha consumer-only hoặc công cụ giám sát sau khi publisher dừng.

### 7.1. Điều cần ghi lại trong pha burst

| Metric | Kết quả cần lấy |
| --- | --- |
| Peak offered và confirmed publish/s | Có thực đạt burst hay bị limit ở producer? |
| Peak ready, unacked, total depth | Broker giữ được bao nhiêu message chờ xử lý? |
| p50/p95/p99 publish confirm latency | Producer có bị nghẽn trước broker? |
| p50/p95/p99 message end-to-end latency | Message chịu bao nhiêu thời gian chờ queue + xử lý? |
| Time to drain | Sau khi rate về bình thường, mất bao lâu để backlog về baseline? |
| Nack, redelivery, DLQ, duplicate | Burst gây lỗi nghiệp vụ/retry storm không? |
| Memory/disk/flow control | Có chạm ranh giới tài nguyên broker không? |

### 7.2. Burst backlog không đồng nghĩa message bị mất

Một hệ thống có thể **chấp nhận backlog tăng ngắn hạn** để bảo vệ DB và vẫn đúng SLO nếu drain kịp. Ngược lại, việc queue ready gần 0 do consumer **AUTO/no-ack trước khi hoàn tất DB** là tín hiệu nguy hiểm chứ không phải thành công.

Vì vậy, acceptance nên được viết dưới dạng:

> “Ở burst X/s trong Y giây, hệ thống không mất message, không tạo duplicate side effect; p99 end-to-end dưới ngưỡng đã thỏa thuận và backlog trở về mức bình thường trong Z phút”.

Không chỉ ghi “TPS > X” mà bỏ thời gian drain, publish outcome và transaction.

## 8. Kiểm thử quá tải: tăng ingress hoặc làm chậm consumer

Có hai cách tạo overload:

- **Tăng tốc độ producer** vượt năng lực xử lý.
- **Giảm tốc độ consumer** qua workload đại diện, ví dụ mô phỏng DB latency/connection pool saturation hoặc giới hạn consumer rate.

PerfTest có thể giới hạn tốc độ consumer (giá trị áp dụng **cho từng consumer**):

```bash
java -jar perf-test.jar \
  --uri amqp://rabbitmq-staging:5672 \
  -x 1 -y 2 -u perf.overload.q \
  -f persistent -s 1024 -q 100 -c 200 \
  --rate 1200 --consumer-rate 200 \
  -z 180 --id overload-backlog
```

Hai consumer × `200/s` tương ứng giới hạn deliver ở phía client khoảng `400/s` trong điều kiện lý tưởng; offered `1200/s` tạo backlog có chủ đích. Đây là **giới hạn tải của mô hình thử**, không chứng minh chính xác consumer thật chỉ xử lý 400/s.

### 8.1. Tách overload ứng dụng và overload broker

| Hiện tượng | Tầng bị nghẽn có thể xảy ra |
| --- | --- |
| Ready tăng, unacked gần `concurrency × prefetch`, DB CPU cao | Consumer/downstream nghẽn; broker vẫn nhận tốt. |
| Publisher confirm latency tăng, connection `flow` | Broker áp dụng flow control tạm thời vì queue/storage/replication không kịp. |
| Connection bị `blocked`, broker báo memory/disk alarm | Giới hạn tài nguyên node khiến broker chặn publisher. |
| Application memory tăng, in-flight futures tăng vô hạn | Producer thiếu bounded concurrency/backpressure. |
| Nack/requeue tăng nhanh, ack/business success gần 0 | Retry storm/poison messages, không phải cần tăng traffic. |

**Không tạo memory/disk alarm bằng cách đổ tải vô hạn vào production.** Chỉ kiểm thử trong staging có quota/disk giới hạn được kiểm soát, có phương án dừng và quan sát resource alerts.

## 9. RabbitMQ flow control và resource alarms

RabbitMQ có ít nhất hai nhóm bảo vệ cần phân biệt:

### 9.1. Transient flow control

Khi publisher gửi nhanh hơn khả năng queue/replication/disk, broker tự điều tiết publishing connection. RabbitMQ Management/CLI có thể hiển thị connection ở trạng thái `flow`. Đây là cơ chế **tạm thời và không cần bật bằng một công tắc riêng**.

Từ góc nhìn producer, publish có thể chậm như thể đường truyền bị giới hạn băng thông. Không nên coi `flow` là sự cố dữ liệu ngay lập tức; nó là tín hiệu đã đến gần một bottleneck. Cần tìm nguyên nhân: queue leader nóng, disk/replication, thiếu consumer hay một topology dồn mọi tải vào một queue.

### 9.2. Memory và disk alarms

Khi memory của node vượt watermark hoặc dung lượng disk trống xuống dưới ngưỡng, RabbitMQ kích hoạt **resource alarm** và có thể **block publishing connections**, nhằm tránh OOM hoặc hết disk. Trong cluster, tác động có thể lan sang các publisher kết nối các node khác.

Hệ quả:

- Publisher call có thể bị chặn lâu, timeout hoặc thất bại.
- Consumer thường vẫn có thể giải phóng backlog, nhưng dùng chung connection/channel cho publish và consume có thể làm quan sát/khôi phục phức tạp hơn; cân nhắc tách connection cho producer và consumer nếu kiến trúc cho phép.
- Publisher confirms có thể về muộn; một timeout **không chứng minh message chưa được broker nhận**.
- Ứng dụng phải ghi nhận **unknown publish outcome** và có chiến lược retry idempotent/outbox.

**Đừng sửa overload bằng cách tăng cao resource watermark đến mức broker bị OOM.** Khi gặp alarm, xác định root cause (queue backlog, memory breakdown, disk free, IOPS, payload size, number of connections) rồi giảm tải hoặc mở rộng tài nguyên có kiểm soát.

### 9.3. Các chỉ số cần quan sát tại broker

```bash
# Chạy trong môi trường staging có quyền rabbitmqctl:
rabbitmqctl status
rabbitmqctl list_queues -p /load \
  name messages messages_ready messages_unacknowledged consumers
rabbitmqctl list_connections name state channels
```

Các lệnh chỉ minh họa cách chụp snapshot; vhost và tên queue phải tương ứng với kịch bản. Ở hệ thống lớn, nên dùng Prometheus plugin và Management API để giữ chuỗi thời gian, không chạy CLI thăm dò quá dày.

Quan sát cả:

- Queue depth/ready/unacked, ingress/deliver/ack/redelivery, queue leader/node placement.
- Memory used, alarm state, disk free, disk I/O, file descriptors, connections/channels.
- Publisher confirmed/nacked/returned/timeout, connection state `flow`/`blocked`, client error rate.
- Consumer latency, DB pool wait, HTTP timeout, thread pool saturation và DLQ.

## 10. Backpressure ở producer Spring AMQP

Nếu một API nhận yêu cầu và gọi `RabbitTemplate.convertAndSend(...)` vô hạn, khi broker chậm, application có thể tích lũy hàng trăm nghìn payload/future trong RAM. Sự cố có thể dịch chuyển từ RabbitMQ sang **OutOfMemoryError ở Spring service**.

Một biện pháp cơ bản là **giới hạn số publish đang chờ confirm** và độ dài hàng đợi nội bộ. Ngoài ra vẫn cần giới hạn request vào, rate limit, batch và durable outbox theo SLA.

### 10.1. Spring Boot config có confirms và returns

```yaml
spring:
  rabbitmq:
    host: rabbitmq-staging
    port: 5672
    virtual-host: /load
    username: load-app
    password: ${RABBITMQ_PASSWORD}
    publisher-confirm-type: correlated
    publisher-returns: true
    connection-timeout: 5s
    template:
      mandatory: true
    listener:
      simple:
        acknowledge-mode: auto
        concurrency: 2
        max-concurrency: 8
        prefetch: 50
        default-requeue-rejected: false
```

Đây là **điểm khởi đầu thử nghiệm**, không phải cấu hình “tối ưu chung”. Prefetch, max concurrency, confirm mode và retry phải đo trên workload thật. Với quorum queues, thứ tự và redelivery có giới hạn riêng; với message lớn hoặc xử lý chậm, prefetch cao làm tăng memory trên consumer.

### 10.2. Publisher có giới hạn số in-flight

Ví dụ `Semaphore` giới hạn tối đa `256` publish đồng thời chưa xác định kết quả. `CorrelationData` cung cấp future cho publisher confirm. Ví dụ sử dụng Java 17+:

```java
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.LongAdder;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class BoundedEventPublisher {
    private final RabbitTemplate template;
    private final Semaphore pending = new Semaphore(256);
    private final LongAdder confirmed = new LongAdder();
    private final LongAdder negative = new LongAdder();
    private final LongAdder rejectedLocally = new LongAdder();
    private final LongAdder unknown = new LongAdder();

    public BoundedEventPublisher(RabbitTemplate template) {
        this.template = template;
    }

    public boolean publish(String eventId, String payload)
            throws InterruptedException {

        // Khi hết capacity: không tạo vô hạn pending futures.
        if (!pending.tryAcquire(250, TimeUnit.MILLISECONDS)) {
            rejectedLocally.increment();
            return false;
        }

        CorrelationData correlation = new CorrelationData(eventId);
        AtomicBoolean released = new AtomicBoolean();
        Runnable releaseOnce = () -> {
            if (released.compareAndSet(false, true)) {
                pending.release();
            }
        };

        correlation.getFuture().whenComplete((confirm, error) -> {
            try {
                if (error != null || confirm == null) {
                    unknown.increment();
                } else if (!confirm.isAck()
                        || correlation.getReturned() != null) {
                    negative.increment();
                } else {
                    confirmed.increment();
                }
            } finally {
                releaseOnce.run();
            }
        });

        try {
            template.convertAndSend(
                    "perf.events", "task.created", payload, correlation);
            return true; // Chỉ có nghĩa đã submit; CHƯA confirmed.
        } catch (RuntimeException exception) {
            unknown.increment();
            releaseOnce.run();
            // Không retry mù: broker có thể đã nhận trước lỗi mạng.
            throw exception;
        }
    }
}
```

Điều kiện áp dụng:

- Spring connection factory phải bật **correlated confirms** và **publisher returns**; template bật `mandatory` nếu muốn quan sát unroutable.
- `getFuture().whenComplete(...)` không mặc nhiên có **timeout deadline**. Khi broker mất kết nối dài hoặc callback không bao giờ về, permits có thể bị giữ; production cần **supervisor theo dõi các publish quá hạn**, xử lý `unknown outcome`, thu hồi in-flight một cách an toàn, và có durable outbox để retry.
- Đếm `confirmed/negative/unknown` trong ví dụ chỉ để diễn giải, chưa phải instrumentation production hoàn chỉnh. Đặc biệt có thể cần **deduplicate kết quả thống kê** khi exception gửi và callback đến ở hai thời điểm; không dùng các counter này làm sổ cái giao nhận.
- `boolean true` trả về là **accepted for attempt**, không đồng nghĩa persisted/processed. Không gửi HTTP 200 “đã xử lý đơn hàng” chỉ dựa vào giá trị này.
- Callback cần ngắn, không chạy DB query chậm trong thread callback. Dùng metrics, logging và durable state machine riêng.

**Đối với API nhận event quan trọng**, cách an toàn hơn là ghi yêu cầu publish vào **Transactional Outbox** rồi publisher worker phát có confirms; admission control giới hạn cả số outbox records chưa xử lý và dung lượng disk/DB. Khi quá tải, trả HTTP 429/503 theo chính sách hoặc tiếp nhận có giới hạn nếu đã **lưu bền vững** thành công. Không báo thành công rồi chỉ giữ event trong hàng đợi RAM không giới hạn.

### 10.3. Vì sao bounded outstanding tốt hơn retry vô hạn?

Khi RabbitMQ bị block:

```text
Không có limit:
  request -> publish future -> timeout -> retry -> futures tăng -> OOM

Có limit + durable retry:
  request -> kiểm tra capacity -> outbox / fail-fast có chủ đích
                              -> chờ confirm có giới hạn
                              -> retry có backoff, idempotency key
```

Retry cần **budget**, jitter/backoff phù hợp và circuit breaker/rate limiter khi downstream không đáp ứng. Đừng retry ngay trong vòng lặp `while(true)` ở callback khi tài nguyên broker đang cạn: đó là cách khuếch đại sự cố.

## 11. Consumer concurrency, prefetch và downstream saturation

### 11.1. Mối quan hệ với throughput

Một listener xử lý đồng bộ mất trung bình `100 ms/message`, khi không chờ các tài nguyên khác, thông lượng lý tưởng của `1 consumer` khoảng `10 message/s`. Với `8 consumer` có thể hướng tới `80/s`, **nhưng chỉ khi** DB/HTTP/CPU/broker có đủ công suất.

Một công thức ước lượng **trần lý tưởng**:

\[
\text{consumer throughput} \lesssim
\frac{\text{concurrency}}{\text{mean service time}}
\]

Đây không phải dự báo hiệu năng chuẩn: service time có phân phối rộng, lock, hot-key, network và queue contention làm thông lượng thấp hơn; thay concurrency có thể tăng p99 do cạnh tranh tài nguyên.

### 11.2. Spring container minh họa

```java
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class PerformanceListenerConfig {
    @Bean("performanceListenerFactory")
    SimpleRabbitListenerContainerFactory factory(
            ConnectionFactory connectionFactory) {
        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setConcurrentConsumers(2);
        factory.setMaxConcurrentConsumers(8);
        factory.setPrefetchCount(50);
        factory.setDefaultRequeueRejected(false);
        factory.setObservationEnabled(true);
        return factory;
    }
}
```

`SimpleMessageListenerContainer` có thể điều chỉnh concurrency trong giới hạn cấu hình khi mức tải thay đổi; không cam kết mở ngay 8 consumer tại thời điểm spike. `DirectMessageListenerContainer` dùng mô hình `consumersPerQueue` khác, cần kiểm thử riêng.

Listener nghiệp vụ:

```java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class TaskListener {
    private final TaskService taskService;

    public TaskListener(TaskService taskService) {
        this.taskService = taskService;
    }

    @RabbitListener(
        queues = "perf.work",
        containerFactory = "performanceListenerFactory")
    public void onMessage(String payload) {
        // Trong thực tế: xử lý đồng bộ và @Transactional nếu dùng DB.
        taskService.applyIdempotently(payload);
        // Chỉ sau khi lời gọi thành công, container mới ack ở AUTO.
    }
}
```

`TaskService` ở ví dụ là service nghiệp vụ do ứng dụng cung cấp. Khi đo performance, dùng DB và dependencies thật hoặc fake có latency được cấu hình rõ; không dùng `Thread.sleep` để thay thế mọi loại I/O rồi suy ra năng lực production.

### 11.3. Đổi một tham số mỗi lần

Thử `concurrency = 2, 4, 8` và `prefetch = 10, 50, 200`, nhưng nên lập **ma trận có kiểm soát**, giữ nguyên offered rate/payload/DB performance ở mỗi lần. Với message lớn, prefetch=200 có thể làm heap tăng. Với yêu cầu **strict ordering**, việc tăng consumer/prefetch có thể làm hành vi thứ tự khó dự đoán; không đánh đổi bảo đảm nghiệp vụ để tối ưu throughput.

| Thay đổi | Có thể tăng | Rủi ro |
| --- | --- | --- |
| Tăng concurrency | Nhiều handler xử lý song song. | DB saturation, lock contention, ordering. |
| Tăng prefetch | Giảm idle do round-trip, tăng pipeline utilization. | In-flight nhiều, memory/uneven distribution, redelivery khi crash. |
| Bật batching / multi-ack | Giảm chi phí giao thức ở workload phù hợp. | Ranh giới ack và một batch lỗi phức tạp hơn. |
| Tăng channel cache | Giảm overhead tạo channel. | Không sửa được DB bottleneck hoặc broker alarms. |
| Thêm queue/shard | Phân tán hot queue/leader, tăng song song. | Routing key, ordering, topology và vận hành phức tạp. |

## 12. Đo end-to-end latency đúng cách

RabbitMQ PerfTest có phép đo latency theo mô hình client của nó; ứng dụng Spring phải đo **từ lúc được chấp nhận publish đến khi business transaction hoàn tất** nếu đó là SLO của hệ thống.

```text
T0: API tiếp nhận/ghi outbox
T1: publish được submit
T2: broker publisher confirm
T3: consumer bắt đầu handler
T4: DB commit thành công
T5: consumer ack broker
```

Các độ trễ khác nhau:

- `T2-T1`: publisher confirm latency, không gồm chờ trong outbox.
- `T3-T2` (xấp xỉ): thời gian ở queue/đợi consumer; có thể âm/khó giải thích nếu timing hoặc clocks khác nhau.
- `T4-T3`: handler + transaction latency.
- `T4-T0`: end-to-end business processing latency theo góc nhìn ứng dụng.
- `T5-T0`: đến thời điểm broker ack, cần broker/client instrumentation để biết chính xác.

**Đừng trừ timestamp giữa hai máy không được đồng bộ** rồi coi đó là kết quả microsecond chính xác. Trong một process, dùng monotonic clock cho duration; giữa producer-consumer, dùng timestamp wall-clock có NTP/PTP phù hợp hoặc distributed tracing với cách diễn giải sai số đồng hồ.

### 12.1. Phân phối latency quan trọng hơn average

Nếu p50=80 ms nhưng p99=12 s, một tỷ lệ nhỏ request đã chịu trễ lớn. Khi burst, p99 có thể tăng mạnh dù average vẫn khá thấp do queueing. Báo cáo tối thiểu **p50, p95, p99, max, sample count** theo từng pha thử, và phân tách **successful**, **failed**, **retried**.

Với Micrometer Observation (Spring AMQP 3.x+), bật `observationEnabled` trên `RabbitTemplate` và listener container có thể đo `spring.rabbit.template` và `spring.rabbit.listener`, bổ sung DB metrics và business timer. Observation của listener **không tự đo thời gian message chờ trong queue**.

## 13. Bộ metrics bắt buộc cho mỗi profile

| Tầng | Cần theo dõi | Mục đích |
| --- | --- | --- |
| Load generator | Offered/s, actual attempts/s, CPU/network, errors, latency. | Bảo đảm nguồn tải không phải bottleneck. |
| Publisher app | Confirm ack/nack, returned, unknown, in-flight, semaphore saturation, retry/outbox lag. | Tách throttle chủ động và broker blocked. |
| Broker queue | Ready, unacked, total depth; enqueue/deliver/ack/redeliver rates; consumer count. | Xác định backlog và tiến độ thật. |
| Broker node | Memory/disk alarms, `flow`/`blocked`, CPU, I/O latency, queue leader, network, connections/channels. | Xác định giới hạn tài nguyên/replication. |
| Consumer app | Concurrent listeners, handler p95/p99, exception rate, DB wait, GC/heap/thread pool. | Xác định bottleneck handler/downstream. |
| Reliability | DLQ depth, retry count, duplicate detection, outbox oldest age, message loss reconciliation. | Không đánh đổi tính đúng lấy thông lượng. |

Prometheus plugin:

```bash
# Chỉ trong môi trường quan sát được phép:
rabbitmq-plugins enable rabbitmq_prometheus
curl -sS http://rabbitmq-staging:15692/metrics
```

Với quan sát queue cụ thể, dùng `/metrics/detailed` và các metric families liên quan, kiểm tra metric labels trên phiên bản RabbitMQ đang chạy. RabbitMQ Management UI/HTTP API giúp xem connection state, queue throughput và alarms để điều tra sự cố. Không lấy sample mỗi vài giây bằng CLI cho hàng nghìn queue như một giải pháp monitoring lâu dài.

### 13.1. Các đường đồ thị nên vẽ chung

1. **Offered / confirmed publish / queue ingress / ack / business completed** (message/s).
2. **Ready, unacked, depth, outbox backlog, DLQ** theo thời gian.
3. **p95/p99 confirm latency**, **p95/p99 handler**, **p95/p99 end-to-end**.
4. **Memory, disk free, CPU, disk IOPS/latency**, queue leader placements.
5. **Flow/blocked state**, reconnect/retry/redelivery counts.

Đặc biệt với burst, đánh dấu **thời điểm bắt đầu spike, kết thúc spike, bắt đầu drain và kết thúc drain** để xác định chính xác recovery time.

## 14. Kịch bản quá tải kết hợp lỗi vận hành

Một hệ thống chỉ được kiểm thử tải trong điều kiện “mọi thứ khỏe” chưa đủ. Tách các kịch bản lỗi để biết năng lực recovery và cách giảm tải có kiểm soát.

### 14.1. Downstream chậm đột ngột

1. Chạy tải nền ổn định.
2. Dùng fault injection ở **database test** để tăng latency hoặc giới hạn pool (không giết DB production).
3. Đo ack rate giảm, ready/unacked thay đổi và publisher có bị flow control khi backlog lớn.
4. Xem listener exception/retry/DLQ; không cho lỗi tạm thời biến thành requeue hot loop.
5. Khôi phục DB; xác minh backlog drain, business completed tăng trở lại và idempotency vẫn đúng.

### 14.2. Broker tạm thời mất kết nối

1. Có publisher confirms, outbox và event ID ổn định trong workload thử.
2. Tạm dừng broker/node hoặc ngắt network trong staging theo topology được kiểm soát.
3. Quan sát publish timeout và **unknown outcome** (có thể broker đã nhận nhưng confirm chưa về).
4. Đưa broker trở lại; kiểm tra Spring listener container recovery, redelivery và retry outbox.
5. Đối chiếu số event ID được lưu bền vững với số business transaction thành công; duplicate delivery không được gây duplicate side effect.

### 14.3. Memory/disk watermark có kiểm soát

1. Ở **node staging riêng**, đặt ngân sách tài nguyên test có giới hạn và cơ chế reset rõ.
2. Tăng backlog hoặc thay đổi tải để quan sát alarm/connection blocked theo chính sách broker.
3. Xác minh producer **không tăng vô hạn** in-flight hay tiêu hết RAM.
4. Giảm ingress và cho consumer drain backlog; xác minh alarm cleared, publish tiếp tục và outbox không mất event.
5. Khôi phục ngưỡng/tài nguyên staging; lưu log/config để test có thể tái lập.

Không tạo lệnh tự động cố làm đầy disk hoặc đẩy broker vào OOM; các phương pháp đó rủi ro và ít giá trị nếu không có giới hạn/phương án rollback.

### 14.4. Poison messages trong lúc burst

1. Cố ý thêm một tỷ lệ nhỏ payload sai schema.
2. Xem consumer có phân loại lỗi, retry có giới hạn/backoff và dead-letter đúng không.
3. Đo redelivery rate, DLQ depth, queue recovery time.
4. Xác nhận throughput của message hợp lệ không bị phá hủy bởi hot retry loop.
5. Sau test, kiểm tra không còn retry chain bất tận.

## 15. Tiêu chí chấp nhận và bảng kết quả mẫu

Không có con số TPS “chuẩn” áp dụng cho mọi hệ thống RabbitMQ. Nên đặt **SLO dựa vào workload và tác động nghiệp vụ**. Ví dụ một phép thử giả định:

| Tiêu chí | Mục tiêu minh họa | Phương pháp chứng minh |
| --- | --- | --- |
| Sustained load | `500 message/s` trong 30 phút. | Offered, confirmed, queue ingress và business completed trung bình. |
| Backlog steady | Không có xu hướng tăng bền vững sau warm-up. | Ready/unacked/depth theo thời gian. |
| p99 end-to-end | Dưới 2 giây khi steady. | Event timestamp/correlation ID, histogram end-to-end. |
| Burst | `1800 message/s` trong 30 giây. | Offered và confirmed thực đạt trong pha spike. |
| Recovery | Backlog trở lại baseline trong 5 phút sau burst. | Đánh dấu mốc kết thúc burst và theo dõi depth. |
| Độ tin cậy | Không mất event đã được ứng dụng chấp nhận lưu bền vững. | Đối soát outbox/event IDs, DB transaction, DLQ/retry outcomes. |
| Overload | Producer fail-fast/queue bền vững có giới hạn, không OOM. | In-flight/outbox metrics, blocked/flow, heap, memory alarms. |

**Các ngưỡng trên chỉ để học cách viết acceptance criteria**, chưa phải đề xuất cấu hình production. Khi cùng một message phải được xử lý ở nhiều consumer group, phép đối soát cần xác định rõ tập consumer/broker/queue nào được tính.

### 15.1. Mẫu bảng điền kết quả thực tế

| Run ID | Rate đặt | Rate thực đã confirm | Rate business success | p99 E2E | Peak ready | Peak unacked | Drain time | Outcome |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| steady-500 | 500/s | [đo] | [đo] | [đo] | [đo] | [đo] | [đo] | PASS/FAIL |
| burst-1800 | 1800/s trong 30 s | [đo] | [đo] | [đo] | [đo] | [đo] | [đo] | PASS/FAIL |
| overload-backlog | 1200/s | [đo] | [đo] | [đo] | [đo] | [đo] | [đo] | PASS/FAIL |
| soak-1h | 500/s | [đo] | [đo] | [đo] | [đo] | [đo] | [đo] | PASS/FAIL |

Điền giá trị đo thật, **không suy đoán** từ target. Kèm phiên bản broker, loại queue, message size, confirms/persistence, prefetch, concurrency, CPU/RAM/disk và commit code để người khác tái hiện.

## 16. Quy trình phân tích kết quả và tối ưu từng bước

### Bước 1: phân biệt producer bottleneck và consumer bottleneck

- Offered lớn nhưng confirmed thấp, in-flight kín, connection `flow`/`blocked`: xem publisher hoặc broker/replication/storage.
- Confirmed≈offered nhưng ready tăng, ack thấp: xem consumer/DB/HTTP.
- Ack cao nhưng business completed thấp: có thể ack quá sớm, duplicate hoặc thiếu instrumentation.
- Deliver/redeliver tăng nhưng business success thấp: phân tích retry/requeue và poison.

### Bước 2: tìm bottleneck đầu tiên

Quan sát CPU và I/O ở cả **load generator, app, DB và RabbitMQ**, không chỉ broker. Nếu database connection pool đã kín, tăng consumer từ 8 lên 32 thường chỉ tăng contention. Nếu một queue leader trở thành hotspot, thêm app consumer có thể không giải quyết giới hạn một node/queue topology.

### Bước 3: thay một nhóm tham số rồi đo lại

Ví dụ thứ tự:

1. Giữ workload và topology, tối ưu xử lý DB/HTTP ở consumer.
2. Thử `prefetch` phù hợp, kiểm tra memory và fairness.
3. Thử concurrency, kiểm tra pool contention và ordering.
4. Điều chỉnh publisher in-flight và batch, bảo đảm confirms không bị vô hiệu.
5. Xem lại số queue/sharding, placement, storage, replication và DLX/retry design nếu broker là bottleneck.

**Không đổi đồng thời** batch, confirms, prefetch, concurrency và queue type rồi kết luận “tăng 3 lần”: không biết yếu tố nào có tác dụng, và có thể đã vô tình loại bỏ một bảo đảm dữ liệu.

### Bước 4: kiểm tra regression

Lưu baseline và chạy lại khi nâng RabbitMQ, Spring AMQP, JVM, DB driver, kernel, disk hoặc thay topology. Với môi trường CI không đại diện production, dùng performance smoke/small load để phát hiện regression lớn; kiểm thử tải dài nên chạy ở môi trường được chuẩn bị riêng.

## 17. Lỗi thường gặp

| Hiện tượng | Sai lầm dễ mắc | Hành động đúng |
| --- | --- | --- |
| “Publish đạt 100k/s, vậy nghiệp vụ đạt 100k/s.” | Bỏ qua routing, consumer ack và DB. | Đo confirmed, ingress, ack và business completed riêng. |
| Ready tăng nhưng thử nghiệm được đánh PASS. | Chỉ xét publisher TPS. | Đánh giá backlog slope, p99 và drain time. |
| Unacked cao bị coi là message mất. | Không hiểu prefetch/manual ack. | Quan sát ack rate, channel state và processing latency. |
| Flow control bị coi là broker hỏng hoàn toàn. | Không phân biệt `flow` và resource alarm. | Kiểm tra memory/disk, queue storage/replication và confirmed rate. |
| Publisher bị block, service OOM. | Không bound in-flight/outbox/retry. | Semaphore/backpressure, admission control, durable outbox. |
| Thử perf bằng nonpersistent và tắt confirm. | Workload không phản ánh bảo đảm production. | Dùng durability, confirms, queue type và replication tương ứng. |
| Spike kết thúc, kết luận hệ thống hồi phục. | Không chờ queue drain. | Đo recovery sau khi tải về baseline. |
| Tăng consumer mãi nhưng throughput không tăng. | Bottleneck ở DB, một queue leader hoặc storage. | Đo downstream/leader CPU, lock, IOPS. |
| Retry làm message/s tăng nhưng success thấp. | Requeue nóng cùng poison message. | Backoff, retry budget, DLQ/parking, idempotency. |
| Test trên laptop được coi là sizing production. | Phần cứng/network/disk không đại diện. | Giới hạn phạm vi kết luận, đo trên staging gần production. |
| Chạy lại test không ra số giống nhau. | Workload, warm-up hoặc môi trường thay đổi. | Pin version, seed, payload, topology, resource quota, thời điểm đo. |
| Resource alarm test làm hỏng dữ liệu thật. | Fault injection trên production. | Chỉ dùng staging cô lập và có phương án reset. |

## 18. Bài thực hành

Chuẩn bị RabbitMQ staging, một Spring Boot producer/consumer có confirms, persistent messages, consumer ack sau xử lý và dashboard. Không dùng dữ liệu thật.

### Bài A — Công suất tải đều

1. Chạy PerfTest baseline `100/s`, `250/s`, `500/s`, mỗi mức ít nhất vài phút sau warm-up.
2. Đo confirmed rate, ack rate, p95/p99, ready/unacked và DB utilization.
3. Tìm mức mà `ack≈ingress` và backlog ổn định; tăng tải cho tới khi thấy điểm mất ổn định.
4. Báo cáo công suất bền vững kèm topology/durability, không chỉ một số TPS.

### Bài B — Burst

1. Chạy `200/s` trong 2 phút, `1800/s` trong 30 giây, sau đó về `200/s`.
2. Ghi peak ready, p99, confirm timeout, thời gian drain đến baseline.
3. Thay `concurrency=2` bằng `4` trong một run riêng; giữ mọi tham số khác.
4. So sánh thời gian drain và DB contention trước khi kết luận việc tăng concurrency có lợi.

### Bài C — Quá tải phía consumer

1. Giữ offered `1200/s`, giới hạn consumer để business rate thấp hơn.
2. Quan sát ready tăng, unacked ở mức prefetch và DLQ nếu có lỗi.
3. Giảm offered rate; đo thời gian hồi phục.
4. Xác minh không mất event và không có pending tasks không giới hạn ở producer.

### Bài D — Broker backpressure/recovery

1. Trong staging cô lập, mô phỏng broker chậm hoặc memory/disk alarm có kiểm soát.
2. Quan sát connection `flow`/`blocked`, publisher pending, confirms/timeouts.
3. Khôi phục broker; đối soát outbox và xử lý trùng qua event ID.
4. Ghi rõ điều kiện thất bại chấp nhận được và giới hạn thời gian recovery.

### Bài E — Soak

Chạy tải nền kéo dài, đo connection/channel count, heap/GC, memory/disk trend, p99 và số message ở DLQ. Kết luận trên đồ thị xu hướng, không chỉ snapshot cuối.

## 19. Câu hỏi tự kiểm tra

1. Vì sao tốc độ `RabbitTemplate.convertAndSend` không chứng minh throughput nghiệp vụ?
2. Tại sao phải bật publisher confirms/persistent delivery khi đó là cấu hình production, dù kết quả test sẽ thấp hơn?
3. Burst `900/s` trong 3 phút và consumer ack `500/s`: backlog tăng xấp xỉ bao nhiêu nếu không có cách loại bỏ message khác?
4. Nếu sau burst ingress về `300/s` và ack `500/s`, 72.000 backlog cần bao lâu để drain theo mô hình đơn giản?
5. Khi nào trạng thái connection `flow` khác với memory/disk alarm khiến publisher bị `blocked`?
6. Tại sao tăng prefetch có thể tăng unacked nhưng không cải thiện business throughput?
7. Vì sao producer cần bound số outstanding confirms và cả backlog outbox?
8. Khi timeout chờ confirm, ta có thể chắc chắn broker chưa nhận message không?
9. Vì sao soak test dài nhiều giờ phát hiện vấn đề mà test 5 phút bỏ sót?
10. Vì sao không được suy ra p99 latency từ công thức `L = λW` bằng một snapshot ready trong pha burst?
11. Khi scale consumer nhưng throughput không tăng, nên kiểm tra những bottleneck nào?
12. Những số liệu nào chứng minh hệ thống đã hồi phục sau overload thay vì chỉ ngừng nhận tải mới?

**Gợi ý đáp án:** (1) gửi ≠ confirm ≠ route ≠ ack ≠ DB success; (2) phải giữ cùng durability guarantee; (3) `(900-500)×180=72.000`; (4) `72.000/(500-300)=360 giây`; (5) flow là điều tiết tạm thời khi producer vượt công suất, alarm là bảo vệ tài nguyên; (6) in-flight nhiều nhưng DB/CPU không nhanh hơn; (7) tránh OOM và backlog không giới hạn; (8) không, outcome có thể unknown; (9) lộ leak/drift/GC/disk growth; (10) không ở steady state; (11) DB, storage, queue leader, network, lock, retry; (12) depth về baseline, p99 phục hồi, business completed, DLQ/duplicates/unknown outcomes được đối soát.

## 20. Tổng kết

**Kiểm thử tải kéo dài** chứng minh ứng dụng và broker giữ được thông lượng, latency và tài nguyên ổn định theo thời gian. **Kiểm thử burst** chứng minh hệ thống hấp thụ đỉnh ngắn hạn và **drain backlog** trong thời gian chấp nhận được. **Kiểm thử quá tải** chứng minh producer/consumer/broker có backpressure, retry có giới hạn, cảnh báo và phục hồi mà không đánh đổi độ tin cậy.

Để tối ưu Spring AMQP đúng cách, cần đo **offered → confirmed → queue ingress → deliver → consumer ack → business completed**, cùng ready/unacked, p95/p99, DLQ, blocked/flow, DB và resource metrics. Chỉ tăng `concurrency` hoặc `prefetch` khi đã xác định nút nghẽn và kiểm tra tác động tới transaction, ordering, redelivery và idempotency.

Một hệ thống bất đồng bộ đáng tin cậy không nhất thiết xử lý ngay mọi burst, nhưng phải **không âm thầm làm mất yêu cầu đã tiếp nhận**, có ranh giới công suất rõ ràng và phục hồi có thể đo lường.

## Tài liệu tham khảo

- [RabbitMQ PerfTest — Official Documentation](https://perftest.rabbitmq.com/): `--rate`, `--variable-rate`, `--consumer-rate`, `-z`, `-f persistent`, prefetch, confirms và workloads.
- [RabbitMQ — Flow Control](https://www.rabbitmq.com/docs/flow-control): transient flow control, connection state `flow` và điều tiết publish.
- [RabbitMQ — Memory and Disk Alarms](https://www.rabbitmq.com/docs/alarms): resource watermark, blocked publishers và bảo vệ broker.
- [RabbitMQ — Monitoring](https://www.rabbitmq.com/docs/monitoring): queue depth, ready, unacked, publish/deliver/ack rates.
- [RabbitMQ — Prometheus and Grafana Monitoring](https://www.rabbitmq.com/docs/prometheus): plugin monitoring, aggregated/detailed metrics và dashboards.
- [Spring AMQP — Listener Concurrency](https://docs.spring.io/spring-amqp/reference/amqp/listener-concurrency.html): `SimpleMessageListenerContainer`, `DirectMessageListenerContainer` và concurrency scaling.
- [Spring AMQP — Asynchronous Consumer](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-consumer.html): prefetch, ordering và consumer trade-offs.
- [Spring AMQP — RabbitTemplate Publisher Confirms and Returns](https://docs.spring.io/spring-amqp/reference/amqp/template.html): xác nhận publish và unroutable messages.
- [Spring AMQP — Micrometer Observation](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/micrometer-observation.html): template/listener observations và cách kết hợp metrics.
