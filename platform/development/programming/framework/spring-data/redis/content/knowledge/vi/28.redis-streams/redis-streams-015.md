# Chính sách retry, bản ghi lỗi và luồng xử lý lỗi riêng trong Redis Streams

Redis Streams cho phép ứng dụng ghi sự kiện thành các bản ghi có ID và nhiều trường dữ liệu, sau đó phân phối công việc cho nhiều consumer qua **consumer group**. So với Redis Pub/Sub, Streams giữ dữ liệu để có thể đọc lại và cung cấp cơ chế theo dõi thông điệp đã giao nhưng chưa xác nhận. Tuy vậy, **Redis Streams không tự quyết định bao nhiêu lần thử lại, khoảng cách giữa các lần thử hoặc khi nào chuyển thông điệp sang luồng lỗi**.

Khi xây một worker xử lý đơn hàng bằng Spring Data Redis, một sự kiện có thể gặp nhiều tình huống:

- Gọi dịch vụ ngoài bị timeout vài giây rồi thành công khi thử lại.
- Nội dung message thiếu trường bắt buộc, thử bao nhiêu lần vẫn lỗi.
- Worker xử lý nghiệp vụ thành công nhưng bị ngắt trước khi gửi `XACK`.
- Worker chết sau khi đọc, để lại message trong **Pending Entries List (PEL)**.
- Message thất bại quá số lần cho phép và cần chuyển sang **dead-letter stream (DLQ/DLS)** để điều tra hoặc xử lý thủ công.

Một chính sách tốt phải phân biệt **lỗi tạm thời**, **lỗi vĩnh viễn**, **lỗi không rõ kết quả**, giới hạn số lần thực thi, thời gian chờ giữa các lần thử và cách lưu thông tin đủ để khôi phục.

## 1. Cơ chế phân phối: XREADGROUP, PEL và XACK

Giả sử ứng dụng có:

```text
Stream chính:       orders:events
Consumer group:     billing-workers
Consumers:          billing-1, billing-2
Stream lỗi riêng:   orders:events:dlq
```

Luồng tổng quát:

```text
Producer
   |
   | XADD orders:events ...
   v
Redis Stream orders:events
   |
   | XREADGROUP GROUP billing-workers billing-1 ... >
   v
Consumer billing-1
   |
   +-- Xử lý thành công --> XACK --> ra khỏi PEL
   |
   +-- Lỗi tạm thời --> chưa ACK
   |                       |
   |                       v
   |                PEL giữ message
   |                       |
   |                 XAUTOCLAIM / XCLAIM
   |                       |
   |                       v
   |                   Thử xử lý lại
   |
   +-- Lỗi vĩnh viễn / quá retry
                |
                v
        XADD orders:events:dlq ...
                |
                v
        XACK message gốc
```

Redis ghi nhận một message vào PEL khi consumer group giao nó cho một consumer và message chưa được xác nhận. Các lệnh liên quan:

| Lệnh | Vai trò |
|---|---|
| `XADD` | Ghi bản ghi mới vào stream |
| `XGROUP CREATE` | Tạo consumer group |
| `XREADGROUP` | Đọc bản ghi trong ngữ cảnh group, giao cho consumer |
| `XPENDING` | Quan sát những bản ghi đã giao nhưng chưa ACK |
| `XACK` | Xác nhận đã xử lý, xóa mục tương ứng khỏi PEL |
| `XCLAIM` | Chuyển quyền sở hữu pending message cụ thể sang consumer khác |
| `XAUTOCLAIM` | Quét và nhận lại các message đã idle đủ lâu |
| `XRANGE` | Đọc bản ghi còn nằm trong stream |
| `XINFO GROUPS` / `XINFO CONSUMERS` | Quan sát tiến độ group, số pending và consumer |

**Cực kỳ quan trọng:** `XACK` **không xóa bản ghi khỏi stream**. Nó chỉ xóa trạng thái pending của message đối với consumer group được chỉ định. Bản ghi vẫn còn trong stream cho tới khi bị `XDEL` hoặc cơ chế trim/xóa phù hợp loại bỏ.

### At-least-once là mô hình thực tế thường gặp

Khi worker chỉ ACK **sau khi** xử lý thành công, một message có thể được gửi lại nếu worker chết trước ACK. Vì vậy mô hình thường được mô tả là **at-least-once processing khi ứng dụng có cơ chế redelivery/reclaim đúng**. Redis không tự chạy một cron retry cho mọi PEL entry; nếu không triển khai recovery, message có thể nằm pending vô thời hạn.

Không thể suy ra “at-least-once” đồng nghĩa xử lý nghiệp vụ **exactly once**. Một message đã gây tác dụng phụ trong database vẫn có thể được xử lý lại nếu ACK bị mất.

## 2. Tạo stream và consumer group để thử nghiệm

Các ví dụ dùng Redis 6.2+ để có `XAUTOCLAIM`, và các key dành riêng cho môi trường test.

Tạo group với stream nếu chưa tồn tại:

```redis
XGROUP CREATE orders:events billing-workers 0 MKSTREAM
```

Trong ví dụ, ID `0` cho phép group đọc các message đã tồn tại trước khi tạo group; nếu muốn group chỉ xem các bản ghi được thêm sau lúc khởi tạo, có thể chọn `$`. Lệnh tạo group sẽ báo `BUSYGROUP` nếu group đã tồn tại — trường hợp này cần được xử lý như “đã khởi tạo”, không phải tạo group mới mỗi lần worker khởi động.

Thêm một bản ghi:

```redis
XADD orders:events * eventId evt-001 orderId ord-42 type PAYMENT_REQUESTED amount 125000
```

Redis trả ID giống:

```text
"1763000000000-0"
```

Đây là **Stream Record ID** do Redis sinh ra, khác với `eventId` nghiệp vụ trong payload. Nên giữ cả hai: ID Redis để thao tác PEL/XACK, còn `eventId` nghiệp vụ để chống xử lý trùng và đối chiếu giữa các hệ thống.

Consumer `billing-1` nhận message mới:

```redis
XREADGROUP GROUP billing-workers billing-1 COUNT 1 BLOCK 1000 STREAMS orders:events >
```

Dấu `>` yêu cầu các bản ghi mới **chưa từng được giao cho consumer group**. Khi message được trả về, nó trở thành pending cho consumer đó.

Quan sát:

```redis
XPENDING orders:events billing-workers
XPENDING orders:events billing-workers - + 10
```

Mẫu kết quả dạng chi tiết của `XPENDING`:

```text
1) "1763000000000-0"    # message ID
2) "billing-1"          # owner hiện tại
3) (integer) 12000      # idle tính bằng mili giây
4) (integer) 1          # số lần Redis ghi nhận delivery
```

Lưu ý: số lần delivery của Redis **không phải số lần hàm Java throw exception**. Nó tăng khi message được giao lại theo cơ chế như đọc lịch sử pending hoặc claim; nếu code xử lý cùng một object nhiều lần mà không redelivery qua Redis, thống kê này không phản ánh các lần đó.

Sau khi thực hiện nghiệp vụ thành công:

```redis
XACK orders:events billing-workers 1763000000000-0
```

Giá trị trả `1` nghĩa là một pending entry được ACK. Lúc này `XPENDING` không còn entry đó, nhưng:

```redis
XRANGE orders:events - +
```

vẫn có thể thấy bản ghi gốc. Đó là hành vi bình thường.

## 3. Phân loại lỗi trước khi chọn retry

Không nên retry tất cả exception giống nhau. Hãy xác định điều kiện nào **có khả năng thay đổi khi chờ**, và điều kiện nào đòi hỏi sửa dữ liệu hoặc can thiệp vận hành.

| Nhóm lỗi | Ví dụ | Chính sách khởi đầu |
|---|---|---|
| **Tạm thời (transient)** | HTTP 503, timeout kết nối, dịch vụ đối tác đang bảo trì | Retry có giới hạn và backoff |
| **Giới hạn tải (throttling)** | HTTP 429 hoặc Redis/DB quá tải | Retry theo `Retry-After` nếu có, thêm jitter |
| **Vĩnh viễn (permanent)** | Thiếu `orderId`, JSON hỏng, schema không hỗ trợ, mã nghiệp vụ không hợp lệ | Không lặp vô ích; chuyển DLQ hoặc đánh dấu từ chối |
| **Không rõ kết quả (ambiguous)** | Đã gửi yêu cầu thanh toán nhưng mất kết nối trước phản hồi | Tra cứu trạng thái theo idempotency key trước khi retry |
| **Lỗi do code/deployment** | `NullPointerException`, cấu hình decoder sai, class không tương thích | Giới hạn retry; cảnh báo và điều tra |
| **Lỗi tài nguyên lâu dài** | Không còn bộ nhớ hoặc không thể ghi DLQ | Không ACK message gốc; phát cảnh báo và khôi phục hạ tầng |

Ví dụ: gọi API thanh toán bị timeout không chứng minh giao dịch thanh toán chưa diễn ra. Nếu retry bằng một request mới không có idempotency key, có thể thu tiền hai lần. Cần ưu tiên xác minh kết quả theo `eventId` hoặc khóa giao dịch ổn định, thay vì chỉ “thử lại 5 lần”.

### Vì sao cần phân biệt nghiệp vụ và hạ tầng?

Một message sai schema cần được đưa tới nơi có thể điều tra payload. Một message thất bại do network có thể được xử lý lại sau vài giây. Nếu cả hai cùng nằm pending chờ một bộ retry vô hạn, hệ thống có thể:

- Gửi đi gửi lại yêu cầu vô ích.
- Gây tải thêm cho dịch vụ đang lỗi.
- Giữ quá nhiều message pending, làm chậm consumer tốt.
- Che khuất bản ghi lỗi nghiêm trọng trong log.

Vì vậy chiến lược thường gồm: **retry có giới hạn**, **backoff**, **DLQ**, **cảnh báo**, và **cơ chế replay có kiểm soát**.

## 4. Chính sách retry: số lần thử, idle time, backoff và jitter

Giả sử xử lý một `PAYMENT_REQUESTED` cho phép tối đa **5 lần xử lý** tính cả lần đầu, với độ trễ tăng dần:

```text
Lần xử lý 1: ngay khi nhận message
Lần xử lý 2: sau ít nhất 2 giây
Lần xử lý 3: sau ít nhất 4 giây
Lần xử lý 4: sau ít nhất 8 giây
Lần xử lý 5: sau ít nhất 16 giây
Sau lần 5 thất bại: ghi DLQ và ACK message gốc
```

Đây là ví dụ **exponential backoff** có giới hạn. Trong thực tế, nên có trần, chẳng hạn 60 giây hoặc 5 phút, và **jitter** để tránh hàng nghìn message cùng retry đúng một thời điểm.

Một công thức minh họa:

```text
delay(n) = min(maxDelay, baseDelay * 2^(n-2)) + randomJitter

Trong đó:
  n = 2, 3, 4... là thứ tự lần thử tiếp theo.
  baseDelay = 2 giây.
  maxDelay = 60 giây.
```

Giới hạn số lần retry không phải luật bất biến: nên dựa trên SLA, độ trễ chấp nhận, độ an toàn của tác dụng phụ, khả năng khôi phục lỗi và chi phí mỗi lần gọi.

### 4.1. Idle time của PEL không đồng nghĩa backoff

`XPENDING` cho biết **idle time** — khoảng thời gian từ lần cuối message được giao hoặc claim. `XAUTOCLAIM` nhận lại những entry đã idle lâu hơn ngưỡng. Đây là công cụ tuyệt vời để **khôi phục message bị kẹt**, nhưng không phải một scheduler biết công thức exponential backoff của nghiệp vụ.

Ví dụ:

```redis
XAUTOCLAIM orders:events billing-workers recovery-1 30000 0-0 COUNT 20
```

Lệnh trên chuyển quyền sở hữu những pending entry đủ điều kiện idle trên 30.000 ms sang consumer `recovery-1`, bắt đầu quét từ `0-0`.

Lệnh trả về:

1. Cursor để quét tiếp, có thể là `0-0` khi hết một lượt.
2. Danh sách message vừa claim được.
3. Ở các phiên bản Redis mới, có thể có danh sách ID đã bị xóa/trim khỏi stream nhưng còn metadata trong PEL.

Với Redis 6.2+, `XAUTOCLAIM` không nhất thiết trả hết các entry trong một lần gọi. Nó quét theo kiểu cursor và có giới hạn lượng PEL được xem xét mỗi lượt; cần sử dụng cursor trả về để tiếp tục quét, và chạy lại theo chu kỳ ngay cả khi trước đó đã kết thúc một lượt. Redis 7.0+ có khả năng dọn một số PEL entry mồ côi khi quét.

**Ngưỡng 30 giây không có nghĩa chính xác 30 giây sau sẽ retry.** Việc retry chỉ xảy ra khi ứng dụng thực sự chạy reclaimer và claim được entry. Nếu job recovery chạy mỗi phút, thời gian chờ thực tế có thể dài hơn.

### 4.2. Không claim quá sớm

Giả sử một worker đang xử lý nghiệp vụ bình thường nhưng có lúc mất 45 giây. Nếu reclaimer claim mọi message idle quá 10 giây, nó có thể lấy message **trong lúc worker ban đầu vẫn đang chạy**:

```text
t0    billing-1 nhận evt-001 và bắt đầu gọi đối tác
t10   recovery-1 XAUTOCLAIM evt-001
t11   recovery-1 cũng xử lý evt-001
t45   billing-1 hoàn tất và chuẩn bị XACK
```

Cả hai worker có thể cùng tạo tác dụng phụ. Chuyển quyền sở hữu PEL **không hủy** tác vụ Java hoặc HTTP request của worker cũ.

Do đó, `min-idle-time` phải được chọn dựa trên timeout và thời lượng xử lý thực tế. Nếu có job rất dài, cần cơ chế heartbeat/lease riêng, chia nhỏ công việc hoặc giới hạn concurrency; không thể lấy một giá trị idle cố định nhỏ hơn thời gian xử lý rồi mong “exactly once”.

### 4.3. Delivery count và số lần thất bại nghiệp vụ

`XPENDING ... - + 10` trả số lần message đã được Redis giao/claim. Chỉ số này tiện để phát hiện poison message, nhưng chưa chắc tương ứng với số lần gọi dịch vụ ngoài. Ví dụ:

- Worker có thể retry trong bộ nhớ ba lần trong **một delivery**.
- Worker bị kill ngay sau khi nhận, chưa thử xử lý nhưng delivery count đã tăng.
- `XAUTOCLAIM ... JUSTID` chỉ lấy ID và **không** tăng delivery counter.
- Một ứng dụng có thể lưu thông tin retry riêng trong Redis/DB và dùng backoff theo lịch.

Nếu policy nói “tối đa 5 lần gọi thanh toán”, hãy lưu **attempt count nghiệp vụ** đáng tin cậy, không coi delivery count mặc nhiên là counter đó.

## 5. Hai chiến lược retry thường dùng

### 5.1. Giữ message trong PEL và claim lại

Quy trình:

```text
XREADGROUP trả message
       |
       v
Xử lý lỗi transient
       |
       +--> KHÔNG XACK
                |
                v
        PEL giữ message
                |
                v
        Background reclaimer XAUTOCLAIM
                |
                v
           Xử lý lại
```

Ưu điểm: không phải tạo bản sao của payload trong một retry stream; Redis đã có PEL và cơ chế claim. Nhược điểm: chờ dựa trên idle và thời gian chạy reclaimer, khó biểu diễn lịch retry động cho từng message, phải quản lý worker đang xử lý chậm.

Phù hợp với những tác vụ có thời lượng tương đối ổn định, muốn ưu tiên khôi phục consumer chết thay vì lịch hẹn retry chính xác.

### 5.2. Dùng retry stream hoặc bộ lập lịch riêng

Ứng dụng có thể đưa message thất bại vào một stream chuyên biệt như `orders:events:retry`, kèm:

```text
originalId    = 1763000000000-0
eventId       = evt-001
attempt       = 2
nextAttemptAt = 2026-11-13T04:20:00Z
errorCode     = PARTNER_TIMEOUT
```

Một thành phần scheduler chỉ chuyển thông điệp đến worker xử lý khi đã tới `nextAttemptAt`. Đây là **logic ứng dụng**, không phải chức năng “delay message” tự động của Redis Stream. Consumer đọc một stream không tự chờ theo trường `nextAttemptAt` của từng record; phải thực thi logic lập lịch.

Một thiết kế khác là Sorted Set, với score là epoch milliseconds của `nextAttemptAt`, rồi một job lấy các ID đến hạn và phát lại vào stream. Với nhiều worker, cần thao tác claim lịch một cách an toàn để tránh cùng lấy một nhiệm vụ.

Ưu điểm: dễ biểu đạt exponential backoff và jitter theo từng event. Nhược điểm: thêm luồng ghi/ACK/chuyển trạng thái, cần idempotency và cơ chế khôi phục nếu tiến trình chết giữa hai thao tác.

### So sánh

| Tiêu chí | PEL + XAUTOCLAIM | Retry stream / scheduler |
|---|---|---|
| Lưu message thất bại | Vẫn trong stream chính và PEL | Có thêm bản ghi/lịch retry |
| Kích hoạt lại | Reclaimer tìm pending idle đủ lâu | Scheduler xác định đã tới `nextAttemptAt` |
| Backoff khác nhau từng message | Khó hơn, cần metadata ngoài PEL | Tự nhiên hơn khi có lịch riêng |
| Nguy cơ xử lý song song khi claim sớm | Có | Có nếu scheduler/claim thiết kế sai |
| Số thành phần cần vận hành | Ít hơn | Nhiều hơn |
| Khôi phục worker crash | Phù hợp | Cần xử lý cả retry state và consumer state |

Hai mô hình có thể kết hợp: dùng PEL để khôi phục consumer chết, còn retry stream/scheduler để quản lý những lỗi transient đã nhận diện rõ.

## 6. Dead-letter stream: lưu gì và khi nào chuyển?

**Dead-letter stream** (thường được gọi DLQ, dù Redis Stream không phải queue truyền thống) là nơi lưu bản ghi mà luồng xử lý chính không thể hoàn tất theo policy:

- Lỗi dữ liệu không thể sửa tự động.
- Lỗi nghiệp vụ không đủ điều kiện retry.
- Đã vượt số lần thử.
- Có tình huống cần người vận hành đánh giá và quyết định.

Ví dụ tạo một bản ghi DLQ:

```redis
XADD orders:events:dlq * originalStream orders:events originalId 1763000000000-0 eventId evt-001 orderId ord-42 errorCode INVALID_AMOUNT attempts 1 failedAt 2026-11-13T04:00:00Z
```

Sau đó mới ACK bản ghi gốc:

```redis
XACK orders:events billing-workers 1763000000000-0
```

### 6.1. Các trường nên lưu trong DLQ

| Trường | Ý nghĩa |
|---|---|
| `originalStream` | Stream nguồn |
| `originalId` | ID bản ghi gốc để đối chiếu |
| `eventId` | ID nghiệp vụ để chống xử lý trùng |
| `payload` hoặc các field cần thiết | Dữ liệu cần để phân tích hoặc replay |
| `errorCode` | Mã lỗi ổn định, ví dụ `INVALID_AMOUNT` |
| `errorMessage` | Mô tả ngắn, tránh lộ bí mật |
| `attempts` | Số lần đã thử xử lý theo policy |
| `firstFailedAt` và `lastFailedAt` | Mốc phát sinh và lỗi mới nhất |
| `consumerGroup`, `consumerName` | Worker/nhóm ghi nhận lỗi |
| `schemaVersion` | Hỗ trợ đọc lại dữ liệu sau khi đổi schema |
| `correlationId` / `traceId` | Liên kết log và request gốc |

Không đưa password, token, số thẻ, dữ liệu cá nhân nhạy cảm hoặc stack trace không được làm sạch vào một DLQ có nhiều người truy cập. Với payload lớn, có thể lưu tham chiếu đến nơi lưu an toàn thay vì sao chép toàn bộ.

### 6.2. DLQ không phải “thùng rác” để bỏ qua mãi mãi

Cần xác định:

1. Ai theo dõi số lượng và độ tuổi message trong DLQ?
2. Khi nào phát cảnh báo?
3. Ai được phép xem/sửa payload?
4. Tiêu chí nào cho phép replay?
5. Dữ liệu DLQ giữ bao lâu; cách trim/xóa ra sao?
6. Nếu một event có lỗi do bug đã được sửa, replay có gây tác dụng phụ lặp lại không?

Nên có dashboard hoặc công cụ vận hành hiển thị `errorCode`, `eventId`, số lần thử và trạng thái xử lý sau khi điều tra.

## 7. Thứ tự an toàn: ghi DLQ rồi mới XACK

Hai lệnh sau không phải lúc nào cũng được thực thi như một transaction:

```text
1. XADD orders:events:dlq ...
2. XACK orders:events billing-workers <id>
```

Nếu **ACK trước**, rồi tiến trình chết trước khi `XADD`, message có thể mất khỏi PEL mà chưa được lưu ở DLQ.

Nếu **XADD trước**, rồi tiến trình chết trước khi `XACK`, message còn pending và có thể bị nhận lại, dẫn đến **hai bản ghi DLQ** nếu không có deduplication.

Thứ tự `XADD → XACK` thường an toàn hơn về khả năng bảo toàn thông tin, nhưng cần cơ chế nhận diện bản ghi DLQ trùng nhau (ví dụ khóa `originalStream + originalId + consumerGroup`, hoặc khóa nghiệp vụ ổn định).

### 7.1. Khi hai key cùng Redis và cùng hash slot

Trong một Redis instance, có thể nhóm `XADD` và `XACK` bằng `MULTI`/`EXEC` để tránh các lệnh client khác xen vào giữa. Tuy nhiên, Redis transaction **không có rollback khi một lệnh lỗi lúc EXEC thực thi**. Không nên gọi đây là giải pháp exactly-once.

Trên Redis Cluster, lệnh nhiều key/transaction thường yêu cầu các key cùng hash slot. Có thể thiết kế:

```text
orders:{billing}:events
orders:{billing}:events:dlq
```

Hai key cùng hash tag `{billing}` nằm cùng slot, giúp hỗ trợ các thao tác đa key cần cùng-slot. Nhưng tập trung quá nhiều nghiệp vụ vào một slot có thể gây **hot shard**; cần thiết kế phân vùng thích hợp thay vì gắn tất cả stream vào một tag toàn hệ thống.

Nếu DLQ nằm ở một hệ thống khác hoặc một Cluster khác, `MULTI`/`EXEC` không thể làm hai nguồn dữ liệu thành một commit nguyên tử. Ứng dụng cần idempotency, retry và cơ chế đối chiếu.

### 7.2. Redis 8.2 và những lệnh xử lý tham chiếu nâng cao

Các phiên bản Redis mới bổ sung lựa chọn điều khiển việc xóa/ACK kết hợp như `XACKDEL` và các policy liên quan consumer groups. Chúng giúp xử lý một số bài toán dọn bản ghi, nhưng không thay thế việc chuyển thông tin thất bại sang DLQ hoặc kiểm soát idempotency. Khi dùng lệnh mới, cần xác nhận phiên bản server và driver Spring Data Redis có hỗ trợ.

## 8. Dùng Spring Data Redis đọc và ACK message

Ứng dụng Spring Boot cần dependency:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
```

Ví dụ `application.yml` cho Redis test:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
```

Các ví dụ dưới đây dùng `StringRedisTemplate` và giá trị field dạng String để dễ quan sát. Nếu ứng dụng dùng serializer JSON/byte tùy chỉnh, các kiểu `MapRecord` và serializer phải được cấu hình nhất quán.

### 8.1. Đọc bằng consumer group

```java
import java.time.Duration;
import java.util.List;
import org.springframework.data.redis.connection.stream.Consumer;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.core.StreamOperations;
import org.springframework.data.redis.core.StreamReadOptions;
import org.springframework.data.redis.core.StringRedisTemplate;

public class OrderStreamPoller {

    private static final String STREAM = "orders:events";
    private static final String GROUP = "billing-workers";

    private final StringRedisTemplate template;

    public OrderStreamPoller(StringRedisTemplate template) {
        this.template = template;
    }

    public List<MapRecord<String, String, String>> poll(String consumerName) {
        StreamOperations<String, String, String> streamOps =
                template.opsForStream();

        return streamOps.read(
                Consumer.from(GROUP, consumerName),
                StreamReadOptions.empty()
                        .count(10)
                        .block(Duration.ofSeconds(1)),
                StreamOffset.create(STREAM, ReadOffset.lastConsumed())
        );
    }
}
```

`ReadOffset.lastConsumed()` trong ngữ cảnh consumer group dùng vị trí **message mới chưa được giao cho group**. Nó không tự động duyệt mọi message đang pending của consumer đã chết. Vì thế, chỉ có poller này là **chưa đủ** để bảo đảm retry/recovery.

Khi dùng `StreamOperations.read(...)` với blocking option, kết quả có thể rỗng hoặc không có message trong khoảng timeout; ứng dụng nên xử lý trường hợp này bình thường, không coi là lỗi nghiệp vụ.

### 8.2. Chỉ ACK sau khi xử lý thành công

Ví dụ logic tối giản:

```java
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.core.StringRedisTemplate;

public class OrderRecordProcessor {

    private static final String STREAM = "orders:events";
    private static final String GROUP = "billing-workers";

    private final StringRedisTemplate template;
    private final BillingService billingService;

    public OrderRecordProcessor(
            StringRedisTemplate template,
            BillingService billingService) {
        this.template = template;
        this.billingService = billingService;
    }

    public void process(MapRecord<String, String, String> record) {
        try {
            billingService.processPayment(
                    record.getValue().get("eventId"),
                    record.getValue().get("orderId"),
                    record.getValue().get("amount")
            );

            template.opsForStream().acknowledge(
                    STREAM, GROUP, record.getId());
        } catch (RuntimeException error) {
            // Không ACK: message vẫn pending để worker recovery xử lý.
            // Cần log có eventId, record ID và loại lỗi.
            System.err.println(
                    "Failed to process " + record.getId() + ": " + error);
        }
    }
}
```

`BillingService` là một interface nghiệp vụ do dự án tự định nghĩa, không phải thành phần Spring Data Redis. Nó phải kiểm tra schema, mã tiền tệ, amount và idempotency trước khi thực hiện tác dụng phụ như gọi cổng thanh toán.

Đoạn mã đơn giản này **chưa phân loại lỗi** và chưa đưa message vào DLQ; nó chỉ minh họa nguyên tắc ACK sau thành công. Trong ứng dụng thật, cần kiểm soát backoff, số attempt và lỗi vĩnh viễn như các mục sau.

### 8.3. Consumer container: đừng dùng auto-ack cho công việc cần retry

Spring Data Redis có `StreamMessageListenerContainer` để quản lý việc polling và dispatch:

```java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.stream.Consumer;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.stream.StreamMessageListenerContainer;
import org.springframework.data.redis.stream.StreamMessageListenerContainer.StreamMessageListenerContainerOptions;

@Configuration
public class OrderStreamConsumerConfig {

    @Bean(initMethod = "start", destroyMethod = "stop")
    public StreamMessageListenerContainer<
            String, MapRecord<String, String, String>> orderListenerContainer(
            RedisConnectionFactory connectionFactory,
            OrderRecordProcessor processor) {

        StreamMessageListenerContainerOptions<
                String, MapRecord<String, String, String>> options =
                StreamMessageListenerContainerOptions.builder()
                        .pollTimeout(Duration.ofSeconds(1))
                        .build();

        StreamMessageListenerContainer<
                String, MapRecord<String, String, String>> container =
                StreamMessageListenerContainer.create(
                        connectionFactory, options);

        container.receive(
                Consumer.from("billing-workers", "billing-instance-1"),
                StreamOffset.create("orders:events",
                        ReadOffset.lastConsumed()),
                processor::process
        );

        return container;
    }
}
```

Trong production, `consumerName` phải phân biệt các instance/consumer đang hoạt động, không gán cùng tên cố định cho nhiều replica tùy tiện. Consumer group **phải được tạo trước** khi container bắt đầu polling, ví dụ qua provisioning hoặc tác vụ khởi tạo có xử lý `BUSYGROUP` và race condition.

Điểm quan trọng là dùng `receive(...)` với ACK **thủ công** sau khi xử lý. `receiveAutoAck(...)` xác nhận message ngay khi nhận, trước khi nghiệp vụ hoàn tất, nên nếu callback lỗi thì message có thể không còn pending để retry. Auto-ACK chỉ phù hợp khi mất thông điệp trong lúc xử lý là chấp nhận được.

Lỗi ở **lớp polling hoặc listener container** cần handler/monitoring riêng; không được giả định mọi exception trong callback đều được Redis tự chuyển thành một retry theo lịch.

## 9. Ví dụ chuyển message lỗi sang DLQ bằng Spring Data Redis

Giả sử processor phát hiện payload không hợp lệ và muốn chuyển sang DLQ ngay, không retry. Bản ghi DLQ nên giữ liên kết tới record gốc.

```java
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.RecordId;
import org.springframework.data.redis.connection.stream.StreamRecords;
import org.springframework.data.redis.core.StringRedisTemplate;

public class DeadLetterWriter {

    private static final String STREAM = "orders:events";
    private static final String GROUP = "billing-workers";
    private static final String DLQ = "orders:events:dlq";

    private final StringRedisTemplate template;

    public DeadLetterWriter(StringRedisTemplate template) {
        this.template = template;
    }

    public void move(
            MapRecord<String, String, String> original,
            String errorCode,
            int attempts) {

        Map<String, String> fields =
                new LinkedHashMap<>(original.getValue());
        fields.put("originalStream", STREAM);
        fields.put("originalId", original.getId().getValue());
        fields.put("consumerGroup", GROUP);
        fields.put("errorCode", errorCode);
        fields.put("attempts", Integer.toString(attempts));
        fields.put("failedAt", Instant.now().toString());

        // Ghi DLQ trước; không ACK khi việc ghi thất bại.
        RecordId dlqId = template.opsForStream().add(
                StreamRecords.newRecord().in(DLQ).ofMap(fields));

        if (dlqId == null) {
            throw new IllegalStateException("Could not append DLQ record");
        }

        // Sau khi DLQ đã được Redis ghi nhận, mới ACK record gốc.
        template.opsForStream().acknowledge(
                STREAM, GROUP, original.getId());
    }
}
```

Đây là ví dụ về **thứ tự ưu tiên an toàn**, không phải một chuyển trạng thái có atomic guarantee giữa `XADD` và `XACK`. Nếu chương trình chết ở khoảng giữa, message có thể được chuyển vào DLQ lần nữa. Một bản triển khai production cần **deduplication**, ví dụ Redis key có định danh `consumerGroup:originalStream:originalId` được tạo bằng cơ chế phù hợp, hoặc một nơi lưu quyết định duy nhất đã xử lý; cần thiết kế đồng bộ với thao tác thêm DLQ.

Nếu `XADD` thất bại, không ACK. Nếu `XACK` thất bại/timeout sau `XADD`, không tự kết luận message gốc đã được ACK hay chưa; lần recovery phải có khả năng đối chiếu DLQ và xử lý idempotent.

### Cấu trúc xử lý theo loại exception

Một workflow có thể được mô tả:

```java
try {
    businessProcessor.handle(event); // phải có idempotency
    streamOps.acknowledge(SOURCE, GROUP, record.getId());
} catch (InvalidEventException permanent) {
    deadLetterWriter.move(record, "INVALID_EVENT", attemptCount);
} catch (TransientPartnerException transientError) {
    // Giữ pending hoặc ghi lịch retry theo policy.
    // Không XACK ở đây nếu chưa chuyển giao trách nhiệm an toàn.
    retryPolicy.recordFailureAndSchedule(record, transientError);
} catch (RuntimeException unknown) {
    // Đánh dấu không rõ kết quả; không retry thiếu kiểm soát.
    incidentReporter.report(record, unknown);
}
```

`InvalidEventException`, `TransientPartnerException`, `retryPolicy` và `incidentReporter` là các kiểu/thành phần **do ứng dụng tự định nghĩa**, nhằm trình bày ý tưởng. Để đưa vào dự án, cần cài đặt chúng cùng kho dữ liệu attempt/backoff/recovery, không copy đoạn pseudocode trên như code chạy độc lập.

## 10. Recovery worker: đọc lại PEL đúng cách

Một consumer group chỉ đọc record mới bằng `XREADGROUP ... >` sẽ **không tự động xử lý lại** record mà consumer cũ đã nhận trước khi chết.

Ví dụ có message pending do `billing-1` sở hữu:

```redis
XPENDING orders:events billing-workers - + 10
```

Một worker khôi phục có thể:

```redis
XAUTOCLAIM orders:events billing-workers recovery-1 60000 0-0 COUNT 10
```

Trong đó:

- `recovery-1` là consumer nhận quyền sở hữu mới.
- `60000` là idle tối thiểu 60.000 ms.
- `0-0` là cursor bắt đầu quét.
- `COUNT 10` giới hạn số record dự định claim trong một lượt.

Sau khi claim thành công, **chính recovery worker phải xử lý các record trả về**, phân loại lỗi, ACK nếu thành công hoặc chuyển DLQ khi đã hết lượt. `XAUTOCLAIM` chỉ chuyển quyền sở hữu; nó không chạy business handler.

### 10.1. Duyệt cursor tới cuối lượt

Ví dụ một kết quả có cursor `1763000000010-0`. Worker phải tiếp tục:

```redis
XAUTOCLAIM orders:events billing-workers recovery-1 60000 1763000000010-0 COUNT 10
```

Khi kết quả trả cursor `0-0`, lượt scan hiện tại hoàn tất. Job có thể nghỉ và chạy lại từ `0-0` sau một khoảng thời gian vì message chưa đủ idle ở lượt trước có thể đủ điều kiện sau đó.

Không cố định “mỗi phút gọi XAUTOCLAIM một lần COUNT 10 từ 0-0” rồi giả định đã khảo sát mọi PEL nếu danh sách pending lớn. Phải quản lý cursor và giới hạn số lượt/độ dài job.

### 10.2. XCLAIM khi đã có ID cụ thể

Nếu quan sát thấy một message ID cụ thể pending quá lâu:

```redis
XCLAIM orders:events billing-workers recovery-1 60000 1763000000000-0
```

`XCLAIM` phù hợp khi đã xác định danh sách ID cần nhận lại. `XAUTOCLAIM` phù hợp hơn để quét các message idle mà không phải tự duyệt `XPENDING` toàn bộ.

Không nên có hai bộ recovery độc lập liên tục claim đi claim lại cùng message. Kể cả khi Redis chuyển ownership đúng, tác vụ của worker cũ có thể đang xử lý dở; vì vậy cần timeout/lease và idempotency.

### 10.3. Retry count của Redis không nhất thiết là policy count

`XCLAIM` và `XAUTOCLAIM` thông thường làm tăng delivery count của message. Nhưng với tùy chọn `JUSTID`, Redis trả chỉ ID và **không** tăng delivery counter. Những biến thể lệnh và các retry nội bộ của ứng dụng có thể làm lệch cách đếm.

Nếu policy cần quyết định “thử xử lý thật tối đa 5 lần”, nên duy trì attempt count nghiệp vụ hoặc quy định rõ chỉ tính các **successful claims that started processing**, thay vì dựa vào delivery count một cách mù quáng.

## 11. Thiết kế retry có backoff mà không chặn worker

Một lỗi thường thấy:

```java
try {
    callPartner();
} catch (Exception error) {
    Thread.sleep(60_000);
    callPartner();
}
```

Nếu đặt cách xử lý này trong listener trực tiếp, một worker giữ luồng xử lý và quyền sở hữu message suốt thời gian ngủ. Với hàng nghìn message lỗi, tài nguyên luồng và khả năng nhận message mới có thể cạn kiệt.

Thay vì ngủ trong handler:

1. Phân loại lỗi và quyết định lần retry tiếp theo.
2. Ghi trạng thái retry bền vững: `attempt`, `nextAttemptAt`, `eventId`, nguyên nhân.
3. Đưa message vào lịch retry hoặc giữ pending theo cơ chế recovery có kiểm soát.
4. Worker hiện tại giải phóng tài nguyên.
5. Một scheduler lấy những message đến hạn và chuyển lại cho consumer.

Khi thiết kế retry stream, chỉ ACK message gốc **sau khi** trách nhiệm retry đã được chuyển giao an toàn, tương tự quy tắc chuyển DLQ. Nếu lịch retry chưa được ghi thành công thì không ACK nguồn.

### Giới hạn áp lực retry

Một policy tốt thường có:

- `maxAttempts` hoặc `maxAge`: chặn vòng lặp vô hạn.
- `baseDelay`, `maxDelay` và jitter: giảm hiệu ứng retry đồng loạt.
- Giới hạn concurrency: tránh tấn công dịch vụ ngoài khi nó đang quá tải.
- Circuit breaker: ngừng gọi liên tục nếu dịch vụ phụ thuộc lỗi diện rộng.
- Phân loại lỗi theo mã ổn định, không theo toàn bộ chuỗi exception.
- Dashboard cho pending, retry và DLQ để phát hiện tiến trình tắc.

Không nên tính retry theo mốc hiện tại duy nhất mà mất toàn bộ lịch sau restart. Message chưa xử lý là trạng thái quan trọng; phải có nguồn dữ liệu để recovery đọc lại.

## 12. Idempotency: điều kiện bắt buộc cho xử lý lại an toàn

Hãy xét luồng:

```text
1. Worker nhận evt-001.
2. Gọi dịch vụ thanh toán -> thành công.
3. Worker crash trước khi XACK.
4. PEL còn evt-001.
5. Reclaimer claim và xử lý evt-001 lần nữa.
```

Nếu không có idempotency, khách hàng có thể bị tính phí hai lần.

### Một cách thiết kế

- Producer gắn `eventId` duy nhất và ổn định với mỗi sự kiện nghiệp vụ.
- Đối với thao tác ghi database, có thể dùng bảng `processed_events(event_id PRIMARY KEY, status, ...)`, cập nhật nó **trong cùng SQL transaction với tác dụng phụ nội bộ**.
- Nếu gọi API ngoài, truyền `eventId` hoặc một idempotency key ổn định tới đối tác nếu API hỗ trợ; nếu phản hồi không rõ, hỏi lại trạng thái bằng key đó.
- Khi gặp cùng `eventId` lần nữa, kiểm tra kết quả trước đó để quyết định ACK, retry hoặc tra soát.

**Cẩn thận với `SET NX` đơn giản trước khi xử lý:**

```redis
SET processed:evt-001 1 NX EX 86400
```

Nếu ứng dụng ghi “đã xử lý” **trước** nghiệp vụ rồi crash, lần redelivery có thể thấy key `processed` và bỏ qua một công việc **chưa hề hoàn tất**. Một khóa tạm/lease hoặc trạng thái `IN_PROGRESS` cần có thời hạn và cơ chế phục hồi; kết quả `DONE` chỉ được xác nhận khi tác dụng phụ thật sự đã thành công.

Kể cả khi dùng Redis làm nơi lưu idempotency, cần phân biệt tạo lock, ghi kết quả và ACK; nếu các hành động trải qua nhiều hệ thống, không có một commit nguyên tử mặc định. Hãy thiết kế cho trường hợp ambiguous result.

## 13. Poison message và nguy cơ chặn luồng xử lý

Một **poison message** là bản ghi liên tục gây lỗi với mọi worker, ví dụ schema sai hoặc dữ liệu khiến decoder ném exception.

Nếu không có `maxAttempts` và DLQ:

```text
evt-001 -> claim -> lỗi -> pending
        -> claim -> lỗi -> pending
        -> claim -> lỗi -> pending
        -> ... lặp mãi
```

Hậu quả là tốn tài nguyên và làm tăng pending/backlog. Nếu message không thể decode ngay từ tầng serialization của listener, callback nghiệp vụ có thể còn **chưa được gọi**; trường hợp này cần error handler ở container/codec và cách khôi phục raw record, không chỉ `catch` trong business processor.

Một chiến lược thực tế:

1. Log mã lỗi và ID message, không in payload nhạy cảm.
2. Nhận diện lỗi schema vĩnh viễn; đưa vào DLQ ngay.
3. Với lỗi chưa xác định, retry hữu hạn và cảnh báo.
4. Nếu DLQ không ghi được, giữ source pending, phát cảnh báo mức cao.
5. Có quy trình phân tích và replay sau khi sửa bug/schema.

Không làm worker crash liên tục chỉ vì một record hỏng mà không có cách cô lập.

## 14. Trim, retention và nguy cơ mất payload pending

Streams giữ bản ghi cho tới khi bị xóa hoặc trim theo policy lưu trữ. Nếu dùng:

```redis
XTRIM orders:events MAXLEN ~ 10000
```

Redis có thể loại bỏ những bản ghi cũ để hạn chế dung lượng. **Không nên mặc định bản ghi pending luôn được giữ lại cho tới khi ACK** trong mọi cấu hình Redis/phiên bản. Một bản ghi bị trim hoặc `XDEL` có thể không còn payload trong stream dù metadata pending từng tồn tại.

Trong Redis 7.0+, `XAUTOCLAIM` có thể nhận diện và dọn một số pending entry không còn bản ghi tương ứng trong stream. Khi đó, recovery không thể khôi phục dữ liệu gốc chỉ từ PEL.

Do đó:

- Xác định retention theo **thời gian xử lý tối đa + thời gian retry/backoff + thời gian downtime chấp nhận**.
- Theo dõi pending lâu nhất trước khi trim quá mạnh.
- Thiết kế retention riêng cho DLQ; message lỗi có thể cần giữ lâu hơn nguồn.
- Nếu dùng Redis 8.2+ với cơ chế kiểm soát tham chiếu khi xóa/trim, cần hiểu semantics cụ thể của policy trước khi thay đổi.
- Với nghiệp vụ cần bền vững cao, đánh giá cấu hình persistence, replication và backup, không chỉ TTL/`MAXLEN`.

**Lưu ý:** `XACK` không xóa bản ghi gốc khỏi stream. Nếu có nhiều consumer group, mỗi group có tiến độ và PEL riêng; xóa bản ghi khi một group đã ACK có thể làm group khác không còn dữ liệu để đọc/khôi phục.

## 15. Redis Cluster, nhiều stream và tính nhất quán

Trong Redis Cluster, những thao tác liên quan nhiều key có thể bị ràng buộc phải ở cùng hash slot. Nếu ứng dụng muốn thực thi logic xử lý giữa source stream và DLQ bằng Lua hoặc `MULTI`/`EXEC`, cần xem xét slot:

```text
orders:{billing}:events
orders:{billing}:events:dlq
orders:{billing}:events:retry
```

Các key chia sẻ `{billing}` nên nằm cùng slot. Tuy nhiên, dồn mọi message vào một hash tag khiến toàn bộ lưu lượng vào một shard, không khai thác phân mảnh. Với nhiều tenant, có thể thiết kế nhóm tag nhỏ hơn như `{billing-tenant42}` và phân phối hợp lý.

Nếu DLQ hay lịch retry nằm ở PostgreSQL, Kafka hoặc Redis Cluster khác, không có một giao dịch Redis duy nhất chuyển trạng thái giữa các hệ thống. Cần log trạng thái, idempotency và cơ chế bù trừ/reconciliation.

### Redis transaction không thay thế kiểm tra lỗi từng lệnh

`MULTI`/`EXEC` có thể gom các lệnh Redis để thực thi không bị xen giữa, nhưng **Redis không rollback các lệnh đã chạy nếu một lệnh sau đó lỗi runtime**. Vì vậy, ngay cả khi source và DLQ nằm cùng slot, ứng dụng vẫn cần kiểm tra:

- Kết quả `XADD` có thành công không?
- `XACK` đã xác nhận đúng message pending chưa?
- Nếu mất phản hồi `EXEC`, có khả năng các lệnh đã chạy không?
- Nếu khởi động lại, có cách nhận diện event đã chuyển DLQ trước đó không?

Đừng dùng tên “transaction” để suy diễn exactly-once hoặc chuyển giao chắc chắn trong mọi tình huống.

## 16. Quan sát hệ thống và cảnh báo

Cần đo cả **lượng message đến**, **tốc độ xử lý**, **độ trễ**, **pending**, **retry**, **DLQ** và **tác dụng phụ**:

| Chỉ số | Mục đích |
|---|---|
| `stream.received.count` | Số message mới được đọc |
| `stream.processed.count` | Số message xử lý thành công |
| `stream.ack.count` | Số message được ACK sau xử lý |
| `stream.pending.count` | Quy mô PEL của group |
| `stream.pending.oldest_idle_ms` | Phát hiện message bị kẹt lâu |
| `stream.retry.attempts` | Số lần thử và phân bố attempt |
| `stream.retry.scheduled.count` | Tồn đọng lịch retry |
| `stream.dlq.count` | Lượng message chuyển DLQ |
| `stream.dlq.oldest_age` | Message lỗi chưa được xử lý lâu |
| `stream.consumer.recovery.count` | Tần suất phải claim lại message |
| `stream.business.duplicate_prevented` | Số redelivery đã được idempotency xử lý an toàn |

Tên metric trong bảng là **gợi ý tự triển khai**, không phải toàn bộ metric Spring Data Redis phát sẵn. Đối với Redis CLI:

```redis
XLEN orders:events
XLEN orders:events:dlq

XINFO GROUPS orders:events
XINFO CONSUMERS orders:events billing-workers

XPENDING orders:events billing-workers
XPENDING orders:events billing-workers IDLE 60000 - + 20

XRANGE orders:events:dlq - + COUNT 10
```

Không dùng `XRANGE stream - +` không giới hạn trên stream production lớn chỉ để debug. Với những stream dài, giới hạn `COUNT` và có cơ chế phân trang bằng ID.

### Các tín hiệu cảnh báo

- Pending count tăng liên tục mà throughput không tăng.
- Message pending idle dài hơn nhiều so với timeout nghiệp vụ.
- Một `eventId` xuất hiện ở nhiều lần retry/DLQ.
- DLQ tăng đột biến theo một `errorCode`.
- Consumer group không tiến triển dù stream liên tục có bản ghi mới.
- Tỷ lệ timeout của dịch vụ ngoài tăng mạnh.
- Số message được ACK nhưng không có bằng chứng tác dụng phụ hoàn tất.
- Retention source stream có nguy cơ xóa các message pending chưa thể xử lý.

Thông tin lỗi phải đủ để vận hành, nhưng tránh lưu credential và payload nhạy cảm vào log hoặc dashboard không kiểm soát quyền truy cập.

## 17. Những lỗi triển khai thường gặp

| Hiện tượng | Nguyên nhân | Hướng khắc phục |
|---|---|---|
| Worker restart rồi bỏ qua message trước đó | Chỉ đọc `XREADGROUP ... >`, không reclaim PEL | Triển khai `XAUTOCLAIM`/`XCLAIM` cho pending |
| Message liên tục retry nhưng không thành công | Không phân biệt permanent/transient | Giới hạn attempt và chuyển DLQ |
| Gọi payment hai lần | Thành công nghiệp vụ rồi crash trước ACK | Idempotency key và đối chiếu trạng thái |
| Đếm số retry lệch | Dùng PEL delivery count như số lỗi nghiệp vụ | Theo dõi attempt theo policy rõ ràng |
| Reclaimer chạy song song với worker đang xử lý | `min-idle-time` quá ngắn | Chọn ngưỡng theo timeout, có lease và idempotency |
| Message bị mất trước khi vào DLQ | ACK nguồn trước khi ghi DLQ | Ghi DLQ trước, ACK sau, có deduplication |
| DLQ có bản ghi trùng nhau | Crash sau XADD DLQ nhưng trước XACK | Dedupe bằng original stream/group/id hoặc eventId |
| Callback lỗi nhưng PEL không còn message | Dùng auto-ack | Chuyển sang manual ACK cho công việc cần retry |
| Không tìm thấy payload khi claim pending | Stream bị trim/xóa trước recovery | Thiết kế retention theo thời gian retry và downtime |
| Retry tạo tải đột biến | Không có backoff/jitter/concurrency limit | Lập lịch có trần và giới hạn |
| Consumer nhận message mới nhưng pending cũ vẫn tăng | Không có recovery job riêng | Đo PEL và chạy reclaimer theo chu kỳ |
| `XAUTOCLAIM` chỉ xử lý được vài message | Bỏ qua cursor, chỉ gọi một lần | Duyệt cursor tới `0-0` và lặp lại về sau |
| Lua/transaction với source và DLQ lỗi CROSSSLOT | Hai stream key khác hash slot | Thiết kế tag phù hợp hoặc không dựa vào multi-key atomicity |
| DLQ tăng nhưng không ai xử lý | Thiếu quy trình vận hành | Đặt alert, owner, công cụ inspect/replay |

## 18. Bài thực hành có thể lặp lại bằng Redis CLI

Thực hiện trong Redis test, dùng key riêng của bài để không ảnh hưởng dữ liệu thực tế.

### Bài 1 — Pending và ACK

1. Tạo stream/group bằng `XGROUP CREATE orders:events billing-workers 0 MKSTREAM`.
2. Ghi hai message bằng `XADD`.
3. Đọc một message với `XREADGROUP GROUP billing-workers billing-1 COUNT 1 STREAMS orders:events >`.
4. Xem `XPENDING` và ghi lại ID, owner, idle, deliveries.
5. `XACK` đúng ID rồi kiểm tra PEL giảm; `XRANGE` vẫn nhìn thấy record gốc.

### Bài 2 — Giả lập worker chết và claim lại

1. `billing-1` đọc một message, **không ACK**.
2. Ngừng consumer hoặc giả lập worker chết.
3. Sau khi idle vượt ngưỡng ở môi trường test, gọi `XAUTOCLAIM` từ `recovery-1`.
4. Quan sát owner mới và delivery count.
5. Dùng `XACK` sau khi hoàn tất xử lý.

Ví dụ lệnh với ngưỡng 5 giây dành riêng cho lab:

```redis
XAUTOCLAIM orders:events billing-workers recovery-1 5000 0-0 COUNT 10
```

Trong production, không lấy ngưỡng 5 giây này làm mặc định nếu xử lý nghiệp vụ có thể lâu hơn.

### Bài 3 — Poison message vào DLQ

1. Ghi message có `amount = invalid`.
2. Consumer đọc, bộ kiểm tra phát hiện lỗi schema vĩnh viễn.
3. `XADD orders:events:dlq` với `originalId`, `eventId`, `errorCode = INVALID_AMOUNT` và thời điểm lỗi.
4. `XACK` message gốc sau khi ghi DLQ thành công.
5. Quan sát `XRANGE orders:events:dlq - + COUNT 10` và `XPENDING`.

### Bài 4 — Lỗi giữa DLQ và ACK

1. Để consumer nhận một message không thể xử lý.
2. Ghi bản ghi DLQ rồi **cố ý dừng chương trình trước `XACK`**.
3. Reclaimer nhận lại message pending.
4. Kiểm tra xem chương trình có nhận diện rằng message đã có trong DLQ không.
5. Thiết kế cách tránh ghi DLQ trùng hoặc cách đánh dấu bản ghi trùng để vận hành có thể xử lý.

### Bài 5 — Retry backoff

1. Chọn `maxAttempts = 4`, các lần đợi 2, 4 và 8 giây.
2. Mô phỏng dịch vụ ngoài lỗi hai lần rồi thành công.
3. Ghi lại `attempt`, `nextAttemptAt`, thời điểm thật sự xử lý.
4. Kiểm tra rằng worker **không sleep giữ luồng listener trong suốt khoảng chờ**.
5. Mô phỏng lỗi cả bốn lần và xác nhận message được chuyển DLQ; không retry vô hạn.

### Bài 6 — Retention khi còn pending

1. Tạo một message pending và cố ý không ACK.
2. Trong môi trường test, trim hoặc xóa bản ghi gốc.
3. Quan sát `XPENDING` và `XAUTOCLAIM` trên phiên bản Redis đang dùng.
4. Giải thích vì sao PEL không phải kho lưu payload thay thế khi stream record đã bị xóa.

## 19. Checklist thiết kế trước khi triển khai

Trước khi đưa worker vào production, trả lời được những câu hỏi sau:

1. Message nào được xử lý lại, message nào chuyển DLQ ngay?
2. Chính sách `maxAttempts` và `maxAge` là gì?
3. Backoff có jitter và giới hạn concurrency không?
4. Ai chạy reclaimer, với `min-idle-time` bao nhiêu và cách duyệt cursor thế nào?
5. Consumer có thể xử lý lâu hơn min-idle không? Nếu có, làm sao tránh xử lý đồng thời?
6. Bản ghi DLQ lưu đủ dữ liệu để điều tra/replay mà không làm lộ thông tin nhạy cảm chưa?
7. Nếu ghi DLQ thành công nhưng ACK lỗi, hệ thống có dedupe không?
8. Nếu nghiệp vụ thành công nhưng ACK lỗi, đã có idempotency chưa?
9. Retention của stream nguồn và DLQ có đủ dài so với downtime/retry không?
10. Có dashboard/alert cho pending, retry, DLQ và các consumer không tiến triển không?
11. Khi ứng dụng deploy schema mới, DLQ cũ có thể được đọc và replay như thế nào?
12. Trên Redis Cluster, các thao tác nhiều key có thỏa hash-slot và giới hạn driver không?

## 20. Kết luận

Redis Streams cung cấp nền tảng cần thiết cho xử lý lại thông điệp bằng **consumer group**, **PEL**, `XACK`, `XPENDING`, `XCLAIM` và `XAUTOCLAIM`. Nhưng Redis không tự chọn số lần retry, không tự tính exponential backoff và không tự đẩy những bản ghi thất bại sang dead-letter stream. Đó là chính sách của ứng dụng.

Đường xử lý nên là: **xử lý thành công rồi ACK**; lỗi transient thì lên lịch retry có kiểm soát; lỗi vĩnh viễn hoặc vượt giới hạn thì **ghi DLQ trước, ACK nguồn sau** và có cơ chế nhận diện bản ghi trùng. Reclaimer phải chủ động thu hồi PEL idle, nhưng không được claim quá sớm khiến hai consumer xử lý cùng lúc.

Cuối cùng, hãy coi việc nhận lại message là một tình huống bình thường. **Idempotency, retention, cảnh báo, khả năng đối chiếu và quy trình replay DLQ** quan trọng không kém những lệnh Redis. Nếu không thiết kế các yếu tố đó, hệ thống có thể vừa mất bản ghi lỗi vừa thực hiện tác dụng phụ hai lần dù Redis Streams vẫn hoạt động đúng.

## Tài liệu tham khảo

- [Spring Data Redis — Redis Streams](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html): `StreamOperations`, consumer groups, listener container và acknowledgment.
- [Spring Data Redis — StreamMessageListenerContainer API](https://docs.spring.io/spring-data/data-redis/docs/current/api/org/springframework/data/redis/stream/StreamMessageListenerContainer.html): `receive`, `receiveAutoAck` và cách đăng ký listener.
- [Redis — Streams data type](https://redis.io/docs/latest/develop/data-types/streams/): producer, consumer group và cơ chế lưu bản ghi.
- [Redis — XREADGROUP](https://redis.io/docs/latest/commands/xreadgroup/): đọc bằng consumer group và ý nghĩa `>`.
- [Redis — XPENDING](https://redis.io/docs/latest/commands/xpending/): quan sát PEL, idle và delivery count.
- [Redis — XACK](https://redis.io/docs/latest/commands/xack/): xác nhận message và gỡ khỏi PEL.
- [Redis — XCLAIM](https://redis.io/docs/latest/commands/xclaim/): chuyển owner của pending message.
- [Redis — XAUTOCLAIM](https://redis.io/docs/latest/commands/xautoclaim/): quét pending theo idle và cursor, các giới hạn và `JUSTID`.
- [Redis — XADD](https://redis.io/docs/latest/commands/xadd/): tạo bản ghi stream và retention tùy chọn.
- [Redis — XTRIM](https://redis.io/docs/latest/commands/xtrim/): dọn stream và tác động đến bản ghi cũ.
