# Pending Entries List và xác nhận xử lý bằng acknowledgment trong Spring Data Redis Streams

## 1. Vì sao Redis Streams cần Pending Entries List?

Redis Streams là cấu trúc dữ liệu dạng log có thứ tự, dùng để ghi và đọc các bản ghi sự kiện. Khác với Pub/Sub thông thường, Stream lưu entry để ứng dụng có thể đọc lại khi cần, theo chính sách retention do hệ thống quyết định. Khi nhiều tiến trình chia nhau công việc bằng **consumer group**, Redis cần biết:

- Message nào đã được giao cho một consumer?
- Message nào chưa được consumer thông báo là xử lý xong?
- Consumer nào đang sở hữu một message?
- Message đã được giao bao nhiêu lần, lần gần nhất khi nào?
- Nếu consumer bị lỗi, ai có thể nhận lại message?

Cấu trúc ghi nhớ trạng thái đó là **Pending Entries List (PEL)**.

**PEL là tập metadata theo dõi các entry đã giao cho một consumer group nhưng chưa được xác nhận bằng acknowledgment (`XACK`).** PEL không phải bản sao độc lập của toàn bộ payload trong Stream. Entry gốc vẫn tồn tại trong Stream theo chính sách lưu trữ của nó.

Bài học tập trung vào hai cơ chế:

1. **Pending:** sau khi một consumer đọc message mới qua `XREADGROUP` và không bật `NOACK`, Redis đưa ID message vào PEL của group.
2. **Acknowledgment:** sau khi xử lý thành công, consumer gọi `XACK` để xóa ID khỏi PEL của group đó.

Sơ đồ vòng đời đơn giản:

```text
Producer
   |
   | XADD
   v
Redis Stream: orders-stream
   |
   | XREADGROUP GROUP orders-workers worker-A STREAMS orders-stream >
   v
Message được giao cho worker-A
   |
   +--> PEL của group "orders-workers" ghi:
   |       ID, consumer=worker-A, idle time, delivery count
   |
   +--> Ứng dụng xử lý dữ liệu
           |
           +-- Thành công --> XACK --> xóa trạng thái pending
           |
           +-- Crash/lỗi --> chưa XACK --> entry tiếp tục nằm trong PEL
                                               |
                                               +--> worker khác claim và xử lý lại
```

Đây là nền tảng của cơ chế xử lý **at-least-once khi ứng dụng triển khai việc retry/recovery phù hợp**. Nó **không tự bảo đảm exactly-once** và cũng không tự động redeliver mọi pending message nếu không có consumer hoặc cơ chế chủ động thu hồi.

## 2. Các khái niệm cần phân biệt

| Khái niệm | Vai trò | Ví dụ |
|---|---|---|
| Stream | Log chứa các entry | `orders-stream` |
| Stream entry ID | Định danh entry trong Stream | `1763000000123-0` |
| Consumer group | Nhóm consumer chia sẻ tiến độ đọc | `orders-workers` |
| Consumer | Thành viên trong group có tên nhận diện | `worker-A` |
| Last-delivered ID | Vị trí giao message mới của group | Một Stream ID |
| Pending Entries List | Danh sách entry đã giao nhưng chưa ACK | ID `...-0` thuộc `worker-A` |
| Acknowledgment | Xác nhận message đã xử lý để bỏ khỏi PEL | `XACK orders-stream orders-workers <id>` |
| Claim | Chuyển ownership message pending sang consumer khác | `XCLAIM`, `XAUTOCLAIM` |
| Stream retention | Chính sách giữ/xóa entry gốc | `XTRIM`, `MAXLEN`, `MINID` |

Cần tách **entry dữ liệu** và **trạng thái xử lý của group**:

```text
Redis Stream (dữ liệu):
    100-0 -> {orderId=o-1, type=CREATED}
    101-0 -> {orderId=o-2, type=PAID}
    102-0 -> {orderId=o-3, type=CANCELLED}

Group orders-workers:
    Last delivered ID: 102-0
    PEL:
        100-0 -> worker-A, pending
        102-0 -> worker-B, pending
    101-0: đã ACK, không còn trong PEL

Group audit-workers:
    Có vị trí đọc và PEL riêng.
```

Một entry có thể đã được ACK bởi group này nhưng còn pending trong group khác. `XACK` **không phải xác nhận toàn cục cho tất cả group**.

## 3. Tạo Stream và consumer group

Giả sử ứng dụng xử lý đơn hàng. Trong Redis CLI, tạo group trước khi đọc:

```redis
XGROUP CREATE orders-stream orders-workers 0 MKSTREAM
```

Ý nghĩa:

- `orders-stream`: tên Stream.
- `orders-workers`: tên consumer group.
- `0`: mốc ID khởi đầu; group có thể đọc các entry hiện có từ đầu Stream.
- `MKSTREAM`: tạo Stream rỗng nếu key chưa tồn tại.

Nếu group cùng tên đã tồn tại, Redis trả lỗi tương tự `BUSYGROUP Consumer Group name already exists`. Trong ứng dụng thực, thao tác tạo group cần có chiến lược khởi tạo idempotent: phân biệt rõ “đã tồn tại” với lỗi quyền truy cập, kết nối hoặc dữ liệu sai kiểu. Không nên bắt mọi exception rồi bỏ qua.

### 3.1. Chọn mốc khởi đầu `0` hay `$`

Có thể tạo group tại thời điểm Stream đã chứa dữ liệu:

```redis
XGROUP CREATE orders-stream orders-workers 0
```

hoặc:

```redis
XGROUP CREATE orders-stream orders-workers $
```

Khác biệt:

| Mốc tạo group | Hành vi mong muốn |
|---|---|
| `0` / `0-0` | Các entry hiện có với ID lớn hơn mốc cũng có thể được giao |
| `$` | Group bắt đầu từ cuối Stream hiện tại, chủ yếu nhận entry mới xuất hiện sau khi tạo group |

Nếu yêu cầu xử lý cả dữ liệu cũ, khởi tạo ở `$` có thể bỏ qua phần lịch sử đã có. Nếu chỉ muốn nhận sự kiện mới, bắt đầu ở đầu Stream có thể khiến dịch vụ xử lý một backlog lớn ngoài dự định.

Chọn mốc dựa vào nghiệp vụ. Thay đổi mốc trên một group đã hoạt động cần được thực hiện có kiểm soát, không nên âm thầm “reset” để chữa một lỗi consumer.

### 3.2. Ghi dữ liệu bằng XADD

```redis
XADD orders-stream * orderId o-101 type CREATED
XADD orders-stream * orderId o-102 type PAID
XADD orders-stream * orderId o-103 type CANCELLED
```

Dấu `*` yêu cầu Redis cấp ID mới. Redis trả về ID thực của entry, ví dụ:

```text
"1763000000123-0"
```

ID trả về ở môi trường thực sẽ khác. Không nên tự giả định ID có đúng giá trị theo ví dụ.

`XADD` thêm entry vào **Stream**, không đưa entry vào PEL. Entry chỉ trở thành pending sau khi được group giao cho consumer trong chế độ tracking thông thường.

## 4. Đọc message bằng XREADGROUP

Consumer `worker-A` đọc message mới:

```redis
XREADGROUP GROUP orders-workers worker-A COUNT 2 STREAMS orders-stream >
```

Giải thích:

- `GROUP orders-workers worker-A`: group và consumer nhận message.
- `COUNT 2`: giới hạn số entry trả về trong một lần đọc, mang tính giới hạn số lượng chứ không phải giới hạn tổng công việc của consumer.
- `STREAMS orders-stream >`: đọc những message **chưa từng được giao cho consumer nào trong group**, theo vị trí group đang theo dõi.
- Không có `NOACK`: những entry được giao được đưa vào PEL.

Mỗi consumer trong cùng group thông thường nhận một phần các entry mới, không phải tất cả consumer đều được broadcast mọi entry như Pub/Sub.

Sau một lần đọc, trạng thái có thể là:

```text
Stream:
    id1 -> o-101
    id2 -> o-102
    id3 -> o-103

Group orders-workers:
    worker-A vừa được giao id1, id2
    PEL:
        id1 -> owner=worker-A
        id2 -> owner=worker-A

id3: vẫn chưa được group giao, chưa nằm trong PEL.
```

`XREADGROUP` có thể nhận thêm:

```redis
XREADGROUP GROUP orders-workers worker-B COUNT 10 BLOCK 5000 STREAMS orders-stream >
```

`BLOCK 5000` chờ tối đa khoảng 5 giây khi chưa có message mới, tính bằng mili giây. `BLOCK 0` mang nghĩa chờ không giới hạn theo cơ chế Redis; trong ứng dụng production cần hiểu tác động đến kết nối và shutdown.

### 4.1. Consumer name là định danh ownership

Tên `worker-A` là một chuỗi do ứng dụng chọn. Redis dùng nó để gắn các pending entry với consumer. Redis không tự biết một process Java đã chết chỉ vì tên consumer còn trong group.

Nếu các process khác nhau cố ý dùng **cùng consumer name**, chúng có thể đọc chung lịch sử pending theo định danh đó, làm khó theo dõi ownership thực tế. Thường nên gán consumer name ổn định trong vòng đời một instance worker, có phân biệt giữa các worker cùng tồn tại.

Cũng cần có kế hoạch khi worker được thay thế: có thể dùng tên mới và claim pending của worker cũ, thay vì chỉ kỳ vọng Redis tự chuyển message.

## 5. PEL được tạo ở thời điểm nào?

Một entry chuyển qua các trạng thái logic:

```text
1. Producer gọi XADD:
      entry ở Stream
      chưa nằm trong PEL của group

2. Consumer gọi XREADGROUP ... >:
      entry được giao cho consumer
      entry vào PEL của group
      ghi owner, thông tin thời gian, delivery count

3. Xử lý thành công nhưng CHƯA XACK:
      vẫn nằm trong PEL

4. Consumer gọi XACK:
      entry được bỏ khỏi PEL của group
      entry vẫn có thể còn trong Stream

5. Nếu xử lý không thành công:
      không XACK
      entry vẫn pending để có thể retry/claim
```

Từ đây rút ra hai điều:

- **“Message đã được đọc” không có nghĩa “message đã được xử lý thành công”.** PEL giữ được sự khác biệt này.
- **“Message không còn pending” không có nghĩa “message bị xóa khỏi Stream”.** Đây là hai vòng đời riêng.

Redis không thể xác nhận nghiệp vụ đã thành công bằng cách nhìn vào method Java. Chỉ khi ứng dụng chủ động ACK thì Redis mới ghi nhận việc hoàn tất ở mức group.

### 5.1. PEL không thay đổi payload của Stream

PEL chứa các thông tin tracking; dữ liệu thực như `orderId`, `type` vẫn nằm trong entry gốc. Khi một consumer khác claim pending, Redis tìm payload theo ID trong Stream.

Nếu entry gốc đã bị xóa hoặc trim trong khi PEL còn ID, quá trình recovery có thể gặp **dangling pending entry** không còn payload. Vì vậy, retention của Stream phải được thiết kế cùng thời gian xử lý và recovery, không thể coi PEL là kho dữ liệu dự phòng.

## 6. Kiểm tra pending bằng XPENDING

Redis cung cấp lệnh `XPENDING` để đọc trạng thái PEL.

### 6.1. XPENDING dạng tổng hợp

```redis
XPENDING orders-stream orders-workers
```

Kết quả logic thường cho biết:

1. Tổng số pending entry trong group.
2. ID nhỏ nhất đang pending.
3. ID lớn nhất đang pending.
4. Các consumer và số lượng entry pending tương ứng.

Ví dụ minh họa:

```text
pending count = 2
smallest id   = 1763000000123-0
largest id    = 1763000000124-0
consumers     = {worker-A: 2}
```

Nếu group không có pending, kết quả tổng hợp phản ánh count bằng 0 và không có khoảng ID tương ứng.

Điểm mạnh của dạng summary là thấy được quy mô backlog đang chờ ACK mà không phải lấy từng entry.

### 6.2. XPENDING dạng chi tiết

```redis
XPENDING orders-stream orders-workers - + 10
```

Trong đó:

- `-`: bắt đầu từ ID nhỏ nhất.
- `+`: tới ID lớn nhất.
- `10`: tối đa 10 entry cần liệt kê.

Mỗi entry thường cho biết:

```text
message ID
owner consumer
idle time (milliseconds)
delivery count
```

Ví dụ logic:

```text
ID: 1763000000123-0
Consumer: worker-A
Idle: 42000 ms
Deliveries: 1
```

Có thể lọc theo consumer:

```redis
XPENDING orders-stream orders-workers - + 10 worker-A
```

Có thể lọc theo thời gian idle tối thiểu trên phiên bản Redis hỗ trợ cú pháp tương ứng:

```redis
XPENDING orders-stream orders-workers IDLE 60000 - + 10
```

Ý nghĩa: xem các entry đang pending và đã idle ít nhất khoảng 60 giây. Khi dùng `IDLE`, cần chú ý cú pháp và khả năng của phiên bản Redis trong môi trường triển khai.

### 6.3. Idle time có phải thời gian xử lý tổng cộng không?

Idle time phản ánh khoảng thời gian tính từ lần giao/claim gần nhất theo metadata PEL. Khi một entry được giao lại hoặc claim, thông tin liên quan có thể được cập nhật. Vì vậy, idle time không nhất thiết bằng tuổi từ lúc `XADD` hoặc thời gian tổng cộng từ khi entry lần đầu vào group.

`delivery count` cũng cần hiểu là số lần giao theo cơ chế Redis, không phải số lần handler chắc chắn đã hoàn thành việc xử lý nghiệp vụ.

### 6.4. Không dùng XPENDING thay cho đọc payload

`XPENDING` phục vụ giám sát ownership và lịch sử giao message. Nó không phải một API tương đương `XREADGROUP ... >` để nhận message mới với payload đầy đủ.

Muốn xử lý pending, có thể đọc lại pending thuộc cùng consumer bằng chế độ đọc lịch sử hoặc chuyển ownership qua `XCLAIM`/`XAUTOCLAIM`.

## 7. Acknowledgment bằng XACK

Sau khi handler hoàn thành công việc cần thiết, gọi:

```redis
XACK orders-stream orders-workers 1763000000123-0
```

Cú pháp:

```redis
XACK <stream-key> <group-name> <id> [id ...]
```

`XACK` xóa những ID được chỉ định khỏi PEL của **consumer group đó**. Giá trị trả về là **số entry đã được xác nhận và loại khỏi PEL**.

Ví dụ:

```redis
XACK orders-stream orders-workers 1763000000123-0 1763000000124-0
```

Kết quả có thể là `2` nếu cả hai ID đang pending trong group và được ACK thành công, hoặc nhỏ hơn nếu một hay nhiều ID không còn pending.

### 7.1. XACK không xóa entry khỏi Stream

Sau ACK:

```text
Stream:
    id1 -> {orderId=o-101, type=CREATED}    (vẫn có thể còn)
    id2 -> {orderId=o-102, type=PAID}       (vẫn có thể còn)

Group orders-workers:
    PEL: không còn id1, id2
```

Có thể quan sát entry gốc bằng:

```redis
XRANGE orders-stream - +
```

Với Stream lớn, không nên dùng `XRANGE - +` không giới hạn trên production. Nên giới hạn số entry:

```redis
XRANGE orders-stream - + COUNT 10
```

Muốn xóa dữ liệu khỏi Stream, sử dụng chính sách retention/trim hoặc lệnh xóa entry phù hợp. Đừng nhầm hành vi dọn PEL với hành vi dọn log.

### 7.2. ACK không có quyền quyết định kết quả nghiệp vụ

Redis không kiểm tra database, email gateway hay tính đúng đắn của code handler trước `XACK`. Nếu ứng dụng ACK sớm rồi mới thực hiện công việc, một lỗi sau ACK có thể làm mất cơ hội retry bằng PEL.

Sai về thiết kế trong nhiều hệ thống:

```text
XREADGROUP -> XACK -> gọi database -> database lỗi
```

Khi đó PEL không còn message, trong khi nghiệp vụ chưa hoàn tất.

Thứ tự thường an toàn hơn:

```text
XREADGROUP -> validate -> xử lý bền vững -> XACK
```

Dù vậy, thứ tự này vẫn có cửa sổ duplicate nếu nghiệp vụ thành công nhưng ACK thất bại. Do đó cần **idempotency** khi yêu cầu độ tin cậy cao.

### 7.3. XACK trả 0 nghĩa là gì?

Nếu gọi `XACK` cho một ID không tồn tại trong PEL của group, Redis có thể trả `0`. Các nguyên nhân:

- Entry đã được ACK trước đó.
- Entry chưa từng được giao cho group.
- Entry đã được xóa khỏi PEL theo một thao tác dọn khác.
- Ứng dụng dùng sai Stream key, group hoặc ID.

Không nên diễn giải `0` đơn giản là “message không tồn tại trong Stream”. Hai câu hỏi khác nhau: **còn pending?** và **còn entry gốc?**

## 8. Một vòng đời đầy đủ bằng redis-cli

Trong môi trường thử nghiệm, có thể dùng tên Stream và group riêng:

```redis
XGROUP CREATE demo:orders demo-workers 0 MKSTREAM
```

Publish hai entry:

```redis
XADD demo:orders * orderId o-201 action CREATED
XADD demo:orders * orderId o-202 action PAID
```

Redis trả ID thực, ký hiệu là `ID_A` và `ID_B` bên dưới. Khi gõ lệnh thực tế, thay hai ký hiệu bằng ID đã nhận từ Redis.

Consumer nhận message:

```redis
XREADGROUP GROUP demo-workers consumer-A COUNT 2 STREAMS demo:orders >
```

Kiểm tra PEL:

```redis
XPENDING demo:orders demo-workers
XPENDING demo:orders demo-workers - + 10
```

Sau khi thực hiện xử lý nghiệp vụ cho `ID_A`, ACK:

```text
XACK demo:orders demo-workers <ID_A>
```

Đây là cú pháp minh họa; `<ID_A>` là chỗ cần điền ID cụ thể trước khi chạy.

Kiểm tra lại:

```redis
XPENDING demo:orders demo-workers
```

Count có thể giảm từ 2 xuống 1. Trong khi đó, các entry gốc vẫn có thể được đọc bằng `XRANGE`.

Cuối cùng, sau khi xử lý thành công `ID_B`, ACK entry còn lại:

```text
XACK demo:orders demo-workers <ID_B>
```

Sau bước này, nếu không có entry pending khác, count về 0. **Stream không tự rỗng chỉ vì PEL rỗng.**

### 8.1. Điều gì xảy ra nếu gọi XREADGROUP lần nữa?

Nếu tất cả entry mới đã được group giao, tiếp tục gọi:

```redis
XREADGROUP GROUP demo-workers consumer-A COUNT 10 STREAMS demo:orders >
```

thì `>` không trả lại những entry còn pending chỉ vì chúng chưa ACK. Cơ chế đọc message mới và cơ chế xử lý pending là **hai luồng riêng**.

Đây là một trong những nguyên nhân phổ biến khiến hệ thống ngừng xử lý một số entry sau crash: consumer mới chỉ đọc `>` và không có tiến trình recovery.

## 9. Đọc lại pending của chính consumer

Trong `XREADGROUP`, ID `>` có ý nghĩa đọc message **mới với group**. Khi chỉ định một ID cụ thể, ví dụ `0`, consumer có thể đọc lại phần lịch sử pending của **chính consumer đó**:

```redis
XREADGROUP GROUP demo-workers consumer-A COUNT 10 STREAMS demo:orders 0
```

Khác biệt chính:

| ID sau tên Stream trong XREADGROUP | Ý nghĩa |
|---|---|
| `>` | Đọc entry chưa được giao cho consumer nào trong group |
| `0` / `0-0` | Đọc những entry pending đã thuộc về consumer name hiện tại, bắt đầu từ vị trí chỉ định |
| Một ID cụ thể | Đọc lịch sử pending của consumer hiện tại sau ID đó, theo quy tắc lệnh |

**Không nhầm đọc pending cùng consumer với nhận ownership của consumer khác.** Nếu `worker-A` chết và `worker-B` gọi `XREADGROUP ... worker-B ... 0`, `worker-B` không tự động lấy toàn bộ PEL đang thuộc `worker-A`.

Để `worker-B` tiếp nhận message pending do `worker-A` sở hữu, cần **claim** bằng `XCLAIM` hoặc `XAUTOCLAIM` (hoặc một cơ chế recovery tương ứng).

### 9.1. Khi nào đọc lịch sử pending cùng consumer hữu ích?

Một consumer dùng tên ổn định có thể khởi động lại và chủ động đọc lại các message nó đã nhận nhưng chưa ACK. Cần xử lý:

- Có message đã xử lý xong trước crash nhưng ACK chưa tới Redis.
- Có message vẫn chưa xử lý.
- Có message gốc đã bị trim/xóa nên không còn payload.
- Có các message được giao lại làm tăng số lần delivery.

Nên bổ sung idempotency, kiểm soát retry và khả năng chuyển entry lỗi sang DLQ nếu không thể xử lý thành công.

## 10. Consumer chết: PEL không tự động biến mất

Giả sử:

```text
t1: worker-A nhận entry id1.
    PEL: id1 -> owner worker-A.

t2: worker-A gọi API thanh toán.
    API xử lý xong nhưng worker-A bị crash trước XACK.

t3: worker-B tiếp tục đọc bằng >.
    worker-B có thể nhận các message MỚI, nhưng không tự thấy id1.

t4: Sau một thời gian:
    PEL vẫn giữ id1 -> worker-A cho đến khi được ACK/claim/dọn theo cơ chế phù hợp.
```

Redis không tự động biết phần nào của nghiệp vụ đã hoàn tất. Việc consumer mất kết nối không phải lời xác nhận rằng message cần được thực hiện lại ngay lập tức.

Nếu worker-B cứ liên tục đọc `>`, id1 có thể pending rất lâu. Hệ thống cần chiến lược phát hiện entry idle quá lâu và cho consumer khác nhận ownership.

## 11. XCLAIM: chuyển ownership một pending entry

Lệnh `XCLAIM` cho phép một consumer yêu cầu chuyển những pending entry đủ điều kiện sang mình.

Cú pháp tiêu biểu:

```redis
XCLAIM <stream> <group> <new-consumer> <min-idle-time-ms> <id> [id ...]
```

Ví dụ:

```redis
XCLAIM demo:orders demo-workers consumer-B 60000 1763000000123-0
```

Giả định ID đã pending và đã idle ít nhất 60.000 ms, Redis có thể chuyển ownership từ `consumer-A` sang `consumer-B` và trả dữ liệu entry.

Thông tin cần chú ý:

- `min-idle-time-ms` không phải TTL của message; đó là **ngưỡng thời gian idle tối thiểu** để có thể claim.
- Claim có thể thay đổi metadata như owner, idle time và delivery count.
- Entry vẫn nằm trong PEL, chỉ chuyển consumer sở hữu.
- Consumer mới cần **xử lý xong rồi XACK**; chỉ claim không phải ACK.
- Nếu consumer cũ vẫn đang chạy chậm, cả consumer cũ và mới có thể xử lý cùng một nghiệp vụ. Claim không thể thu hồi side effect đã khởi chạy từ code của consumer cũ.

### 11.1. Chọn min-idle-time hợp lý

Nếu một công việc thường mất 3 phút, đặt `min-idle-time` 5 giây có thể khiến worker khác claim trong lúc worker đầu vẫn xử lý bình thường, gây duplicate và tranh chấp.

Nếu đặt quá dài, entry thật sự bị bỏ dở có thể mất nhiều thời gian để được retry.

Nên cân nhắc:

- Thời gian xử lý trung bình và p99.
- Timeout của tác vụ và API phụ thuộc.
- Cơ chế heartbeat/ownership mà ứng dụng triển khai thêm nếu có.
- Chi phí của việc thực hiện trùng.
- Yêu cầu tối đa về thời gian khôi phục sau crash.

Không có một giá trị 60 giây phù hợp mọi workload. Ngưỡng trong ví dụ chỉ nhằm minh họa.

## 12. XAUTOCLAIM: tự tìm và claim pending idle

Redis 6.2 trở lên hỗ trợ `XAUTOCLAIM`, giúp quét PEL theo cursor và claim những entry đã idle đủ lâu.

Cú pháp thường gặp:

```redis
XAUTOCLAIM <stream> <group> <consumer> <min-idle-time-ms> <start> [COUNT <count>]
```

Ví dụ:

```redis
XAUTOCLAIM demo:orders demo-workers consumer-B 60000 0-0 COUNT 10
```

Lệnh tìm các pending entry đã idle đủ lâu bắt đầu từ ID `0-0`, claim những entry phù hợp sang `consumer-B` rồi trả về thông tin cursor tiếp theo và các message đã claim. Với Redis phiên bản có thêm phản hồi về ID bị dọn do entry gốc không tồn tại, phần response có thể chứa thêm danh sách đó.

**XAUTOCLAIM không có nghĩa hệ thống tự chạy recovery định kỳ.** Đây là lệnh ứng dụng phải gọi. Muốn recovery tự động, cần một worker/scheduler hoặc vòng lặp recovery có giới hạn.

### 12.1. Cursor và COUNT

`XAUTOCLAIM` dùng cursor để tránh phải quét toàn bộ PEL trong một lần. Ứng dụng cần giữ cursor trả về và tiếp tục quét nếu còn cần, thay vì luôn mặc định chỉ chạy `0-0` một lần rồi coi như đã xem hết pending.

`COUNT` là số entry tối đa mong muốn claim trong một lần, còn lượng entry nội bộ được xét có giới hạn theo cơ chế Redis. Không nên diễn giải mỗi lần gọi luôn trả đúng `COUNT` entry hoặc luôn quét hết PEL.

Khi cursor trả `0-0`, một vòng quét hiện tại đã đến cuối phạm vi được xét. Điều đó không bảo đảm PEL sẽ mãi không còn entry đủ điều kiện: thời gian idle của entry khác tiếp tục tăng, message mới tiếp tục được giao và pending có thể xuất hiện.

### 12.2. Vòng lặp recovery ở mức ý tưởng

```text
cursor = "0-0"

Lặp với số lần/giao dịch được giới hạn:
    response = XAUTOCLAIM(stream, group, recoveryConsumer,
                          minIdle, cursor, COUNT 20)
    cursor = response.nextCursor

    Với từng message đã claim:
        nếu xử lý thành công:
            XACK(stream, group, message.id)
        nếu xử lý thất bại:
            giữ pending, ghi nhận lỗi, chờ retry/bù

    Nếu cursor == "0-0":
        kết thúc vòng scan hiện tại
```

Cần có cơ chế backoff, rate limiting và tránh nhiều recovery workers cạnh tranh cùng lúc quá mạnh. Đừng để tác vụ recovery quét PEL với tốc độ không giới hạn, gây ảnh hưởng đến xử lý message mới.

### 12.3. XCLAIM hay XAUTOCLAIM?

| Tình huống | Lựa chọn |
|---|---|
| Đã biết chính xác ID cần chuyển owner | `XCLAIM` |
| Cần quét các entry pending đã idle lâu để lấy lại việc | `XAUTOCLAIM` |
| Cần thống kê pending, consumer và idle | `XPENDING` |
| Cần đọc message mới | `XREADGROUP ... >` |
| Cần đọc pending của cùng consumer name | `XREADGROUP ... 0` |
| Xử lý xong và muốn bỏ pending | `XACK` |

Đối với hệ thống lớn, `XAUTOCLAIM` thường thuận tiện hơn quy trình `XPENDING` liệt kê ID rồi lần lượt `XCLAIM`, nhưng vẫn cần quản lý cursor, concurrency và idempotency.

## 13. Phân biệt pending với failed và retry

Một entry pending **không đồng nghĩa** là entry thất bại. Nó có thể đang được một worker xử lý bình thường hoặc đã xử lý xong nhưng ACK chưa đến Redis.

```text
Pending =
    "Redis đã giao cho group, chưa nhận ACK"

Failed =
    "Application biết lần xử lý này đã thất bại"

Retryable =
    "Application quyết định công việc có thể chạy lại"
```

Ba khái niệm này cần được quản lý riêng.

Một thiết kế lỗi thường gặp:

```java
try {
    processOrder(record);
} catch (Exception ex) {
    // Giữ nguyên pending để recovery sau.
}
```

Nếu không có hệ thống ghi nhận, giới hạn retry hoặc dead-letter handling, message lỗi vĩnh viễn sẽ bị kẹt pending mãi. Ngược lại, nếu ACK ngay trong `finally`, có thể đánh dấu hoàn tất cả những công việc chưa xử lý.

### 13.1. Những loại lỗi nên phân biệt

| Loại lỗi | Ví dụ | Hướng ứng xử |
|---|---|---|
| Lỗi tạm thời | Database timeout, API 503 | Retry có backoff và giới hạn |
| Lỗi payload không hợp lệ | Thiếu `orderId`, sai schema | Chuyển DLQ/ghi sự kiện lỗi có chủ đích |
| Lỗi nghiệp vụ không thể xử lý | Đơn hàng không có trạng thái hợp lệ | Tùy chính sách: ghi nhận từ chối hoặc DLQ |
| Consumer crash | Process chết giữa xử lý | Recovery pending bằng `XCLAIM`/`XAUTOCLAIM` |
| ACK thất bại sau khi xử lý thành công | Mất kết nối Redis | Có thể bị xử lý lại; cần idempotency |
| Entry gốc đã bị trim | PEL còn ID nhưng không còn payload | Xử lý dangling pending, điều chỉnh retention |

PEL chỉ cung cấp trạng thái delivery. Quyết định **retry, drop, cảnh báo hay chuyển DLQ** thuộc ứng dụng.

## 14. Mẫu xử lý chuẩn: chỉ ACK sau thành công

Một consumer có thể xử lý theo luồng:

```text
Bắt đầu:
    XREADGROUP lấy message

Validate:
    Kiểm tra id, schema, dữ liệu bắt buộc

Idempotency:
    Kiểm tra eventId/orderId đã được xử lý chưa

Business transaction:
    Ghi dữ liệu bền vững hoặc thực hiện side effect được kiểm soát

Sau khi thành công:
    XACK message.id

Nếu lỗi:
    Không XACK bừa bãi
    Ghi nhận lỗi
    Cho retry/recovery hoặc chuyển DLQ theo chính sách
```

Điểm khó là **transaction nghiệp vụ và XACK không tự nguyên tử qua hai hệ thống**. Nếu dữ liệu nguồn nằm trong PostgreSQL, một transaction SQL commit thành công không khiến Redis `XACK` chắc chắn thành công. Và nếu `XACK` thành công trước commit SQL, crash có thể gây mất công việc.

### 14.1. Cửa sổ duplicate khi ACK đến sau commit

```text
t1: Worker nhận event E.
t2: Worker cập nhật bảng orders; SQL COMMIT thành công.
t3: Worker crash trước XACK.
t4: E vẫn ở PEL.
t5: Recovery claim E và gọi handler lại.
```

Nếu handler trừ tiền hoặc gửi email một lần nữa, hệ thống có thể tạo side effect trùng.

Vì vậy, thiết kế at-least-once thực tế cần **idempotent consumer**.

### 14.2. Idempotency theo eventId

Mỗi event nên có ID nghiệp vụ ổn định:

```json
{
  "eventId": "evt-1001",
  "orderId": "o-101",
  "type": "OrderPaid",
  "amount": 150000
}
```

Ở phía hệ thống sở hữu dữ liệu, có thể dùng bảng:

```sql
CREATE TABLE processed_events (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
```

Trong **cùng transaction SQL** với cập nhật nghiệp vụ, cố gắng insert `event_id` duy nhất. Nếu insert bị trùng, handler biết event này đã được áp dụng trước đó và có thể bỏ qua side effect lần hai rồi ACK.

Đây là hướng thiết kế khái niệm. Logic SQL thật cần tương thích database, xử lý unique constraint và ràng buộc nghiệp vụ. Nếu nghiệp vụ có side effect bên ngoài SQL (như email hoặc payment gateway), cần thêm outbox, idempotency key của provider hoặc cơ chế bù/đối soát.

Không nên suy rằng lưu một Redis key "đã xử lý" bằng `SETNX` ở một bước riêng luôn bảo đảm đồng bộ nguyên tử với commit database.

## 15. Spring Data Redis: đọc bằng StreamOperations

Spring Data Redis cung cấp `StreamOperations` để làm việc với Redis Streams ở mức Java. Ví dụ sau dùng `StringRedisTemplate` với key và field dạng String.

Dependency Spring Boot:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis</artifactId>
</dependency>
```

Cấu hình kết nối Redis ví dụ:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
```

Khởi tạo Stream/group bằng Redis CLI:

```redis
XGROUP CREATE orders-stream orders-workers 0 MKSTREAM
```

Hoặc tạo group bằng API của Spring Data Redis khi phù hợp, có xử lý tình huống group đã tồn tại:

```java
StreamOperations<String, String, String> ops =
    stringRedisTemplate.opsForStream();

ops.createGroup(
    "orders-stream",
    ReadOffset.from("0-0"),
    "orders-workers"
);
```

Đoạn Java giả định các import sau:

```java
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.core.StreamOperations;
```

Việc tạo group khi Stream chưa tồn tại có thể cần tạo Stream trước hoặc chọn API/cơ chế khởi tạo phù hợp phiên bản. Lệnh CLI có `MKSTREAM` rõ ràng hơn trong ví dụ đầu. Không nên tạo group vô điều kiện mỗi lần worker khởi chạy mà không xử lý `BUSYGROUP`.

### 15.1. Đọc group với ReadOffset.lastConsumed()

Ví dụ service polling:

```java
package com.example.orders;

import java.time.Duration;
import java.util.List;

import org.springframework.data.redis.connection.stream.Consumer;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.core.StreamOperations;
import org.springframework.data.redis.core.StreamReadOptions;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderStreamWorker {

    private static final String STREAM = "orders-stream";
    private static final String GROUP = "orders-workers";

    private final StringRedisTemplate redis;
    private final OrderEventHandler handler;

    public OrderStreamWorker(
            StringRedisTemplate redis,
            OrderEventHandler handler) {
        this.redis = redis;
        this.handler = handler;
    }

    public void pollOnce(String consumerName) {
        StreamOperations<String, String, String> ops =
            redis.opsForStream();

        List<MapRecord<String, String, String>> records =
            ops.read(
                Consumer.from(GROUP, consumerName),
                StreamReadOptions.empty()
                    .count(10)
                    .block(Duration.ofSeconds(2)),
                StreamOffset.create(
                    STREAM,
                    ReadOffset.lastConsumed()
                )
            );

        if (records == null || records.isEmpty()) {
            return;
        }

        for (MapRecord<String, String, String> record : records) {
            try {
                handler.handle(record);

                // Chỉ xác nhận SAU KHI handler thành công.
                Long acknowledged = ops.acknowledge(
                    STREAM,
                    GROUP,
                    record.getId()
                );

                if (acknowledged == null || acknowledged == 0L) {
                    // Log/metric: ID đã không còn pending ở group.
                }
            } catch (Exception failure) {
                // Log có ngữ cảnh ID/consumer; không ACK bừa bãi.
                // Message vẫn pending để được recovery theo chính sách.
            }
        }
    }
}
```

`OrderEventHandler` là interface nghiệp vụ do ứng dụng định nghĩa, ví dụ:

```java
package com.example.orders;

import org.springframework.data.redis.connection.stream.MapRecord;

public interface OrderEventHandler {
    void handle(MapRecord<String, String, String> event);
}
```

Các điểm cần hiểu:

- `Consumer.from(GROUP, consumerName)` xác định group và consumer nhận entry.
- `StreamOffset.create(STREAM, ReadOffset.lastConsumed())` diễn đạt cách đọc entry mới cho consumer group (tương ứng ý định `>`).
- `count(10)` giới hạn số entry một lần đọc.
- `block(Duration.ofSeconds(2))` chờ có giới hạn để ứng dụng có thể kiểm soát vòng polling và shutdown.
- `ops.acknowledge(...)` là bước xác nhận xử lý và loại ID khỏi PEL.
- `handler.handle(...)` cần xử lý idempotent nếu muốn an toàn trước duplicate.
- Catch lỗi không ACK chỉ phù hợp khi có **recovery/poison-message policy**; nếu không, pending có thể tồn đọng mãi.

`pollOnce` chỉ là một lượt poll, không phải một hệ thống worker hoàn chỉnh có scheduler, lifecycle, shutdown hoặc recovery. Trong production cần thành phần điều phối chạy polling và giám sát lỗi.

### 15.2. Vì sao không dùng ReadOffset.latest() theo thói quen?

Spring Data Redis có các `ReadOffset` khác nhau để diễn đạt vị trí đọc. Với consumer group, muốn nhận entry chưa giao cho group theo tiến độ đã lưu, cần dùng offset thích hợp, thường là `ReadOffset.lastConsumed()`.

`ReadOffset.latest()` mang ý nghĩa đọc từ mốc cuối hiện tại ở những kiểu đọc tương ứng; dùng sai offset có thể làm bỏ qua entry, nhất là với polling. Không nên coi mọi offset là tương đương `>`.

### 15.3. Bảo đảm serializer

`StringRedisTemplate` hỗ trợ key và value dạng String. Với `MapRecord`, các field/value trong ví dụ được xem như String. Nếu producer dùng JSON hoặc binary serializer khác, handler phải deserialize đúng format.

Dù payload được giải mã thành object kiểu nào, **Stream ID** là định danh quan trọng để ACK. Đừng tự tạo ID mới để gọi `acknowledge`, cũng đừng dùng `orderId` thay cho Redis Stream entry ID.

## 16. StreamMessageListenerContainer và xác nhận thủ công

Ngoài polling bằng `StreamOperations`, Spring Data Redis có `StreamMessageListenerContainer` để quản lý vòng đời poll/dispatch message từ Stream.

Sơ đồ:

```text
Redis Stream
    |
    v
StreamMessageListenerContainer
    |
    v
StreamListener.onMessage(record)
    |
    +--> process business
    |
    +--> acknowledge via StreamOperations
```

Ví dụ cấu hình container (dạng API phổ biến):

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

@Configuration
public class OrderStreamContainerConfig {

    @Bean
    StreamMessageListenerContainer<String, MapRecord<String, String, String>>
    orderStreamContainer(
            RedisConnectionFactory connectionFactory,
            OrderStreamListener listener) {

        var options =
            StreamMessageListenerContainer
                .StreamMessageListenerContainerOptions
                .builder()
                .pollTimeout(Duration.ofSeconds(1))
                .build();

        StreamMessageListenerContainer<String, MapRecord<String, String, String>>
            container = StreamMessageListenerContainer.create(
                connectionFactory,
                options
            );

        container.receive(
            Consumer.from("orders-workers", "worker-A"),
            StreamOffset.create(
                "orders-stream",
                ReadOffset.lastConsumed()
            ),
            listener
        );

        container.start();
        return container;
    }
}
```

Trong dự án thật, lifecycle container nên được Spring quản lý phù hợp; tránh start nhiều lần hoặc tạo trùng subscription khi cấu hình bean. Kiểu generic và builder option có thể cần điều chỉnh theo phiên bản Spring Data Redis của dự án, đặc biệt khi dùng template serializer hoặc các dạng record khác.

Một listener có ACK thủ công:

```java
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.stream.StreamListener;
import org.springframework.stereotype.Component;

@Component
public class OrderStreamListener
        implements StreamListener<String, MapRecord<String, String, String>> {

    private final StringRedisTemplate redis;
    private final OrderEventHandler handler;

    public OrderStreamListener(
            StringRedisTemplate redis,
            OrderEventHandler handler) {
        this.redis = redis;
        this.handler = handler;
    }

    @Override
    public void onMessage(MapRecord<String, String, String> record) {
        try {
            handler.handle(record);

            redis.opsForStream().acknowledge(
                "orders-stream",
                "orders-workers",
                record.getId()
            );
        } catch (Exception failure) {
            // Không ACK nếu handler chưa hoàn tất.
            // Ghi log, metric; để recovery xử lý theo chính sách.
        }
    }
}
```

Ở đây listener thực hiện ACK sau handler, vì ta muốn kiểm soát thời điểm xác nhận. Không nên dùng đồng thời listener manual ACK và một cấu hình auto-ack khác cho cùng flow mà chưa hiểu rõ thứ tự thực thi.

### 16.1. auto-ack và manual ACK

Một số overload đăng ký consumer trong listener container có hỗ trợ **auto-acknowledgment** theo contract tương ứng. Khi auto-ack, thời điểm ACK do container quyết định, thường gắn với việc dispatch/callback đã hoàn thành theo cơ chế implementation.

Nếu nghiệp vụ cần commit database, gọi API ngoài hoặc ghi outbox trước khi xác nhận, nên hiểu rõ auto-ack có phù hợp không. Với ví dụ yêu cầu `handler.handle` thành công trước ACK, manual ACK giúp thể hiện thứ tự rõ ràng hơn.

Auto-ack không tự bảo đảm mọi side effect đã thành công, đặc biệt nếu listener bắt exception và nuốt lỗi hoặc chuyển việc xử lý sang một thread khác rồi trả về sớm.

### 16.2. Callback chậm và giới hạn tải

Nếu handler mất nhiều giây, quá nhiều message được giao cùng lúc có thể làm tăng pending và thời gian idle. Cần chọn:

- Số consumer thực sự chạy.
- Batch size/COUNT.
- Số luồng xử lý và mức concurrency.
- Timeout và backpressure.
- Thời gian xử lý so với ngưỡng auto-claim.
- Cách shutdown để tránh bỏ dở lượng lớn message.

Không nên tăng số consumer mà không kiểm tra cơ sở dữ liệu gốc có chịu được tải không.

## 17. Monitoring: lag và pending không giống nhau

Để biết nhóm worker hoạt động tốt hay không, cần ít nhất hai góc nhìn:

1. **Lag/new backlog:** có bao nhiêu entry chưa được group giao ở mức chỉ số khả dụng.
2. **Pending backlog:** có bao nhiêu entry đã giao nhưng chưa được ACK.

Redis có các lệnh:

```redis
XINFO STREAM orders-stream
XINFO GROUPS orders-stream
XINFO CONSUMERS orders-stream orders-workers

XPENDING orders-stream orders-workers
XPENDING orders-stream orders-workers - + 20
```

`XINFO GROUPS` có thể cung cấp số `pending`, `last-delivered-id` và `lag` khi phiên bản Redis hỗ trợ và lag có thể tính được. Trong các tình huống tạo group/đổi vị trí/trim đặc biệt, lag có thể không có hoặc không phản ánh đơn giản toàn bộ backlog; không nên coi nó là chỉ số tuyệt đối trong mọi trường hợp.

Một trạng thái quan trọng:

```text
Group lag:     0
Group pending: 500
```

Điều này có thể nghĩa là Redis đã giao hết entry mới cho group, **nhưng 500 entry vẫn chưa được ACK**. Hệ thống chưa chắc đã xử lý xong công việc.

Ngược lại:

```text
Group lag:     10.000
Group pending: 0
```

có thể là group còn rất nhiều entry chưa được giao nhưng không có entry đang chờ ACK. Cần tăng khả năng đọc/processing chứ không nhất thiết cần recovery pending.

### 17.1. Những metric vận hành nên thu thập

| Chỉ số | Ý nghĩa |
|---|---|
| Stream length (`XLEN`) | Số entry còn được giữ trong Stream, không phải backlog chính xác của một group |
| Pending count | Số entry đã giao nhưng chưa ACK |
| Pending oldest idle | Gợi ý entry có thể đang kẹt |
| Per-consumer pending | Tải đang chờ ACK theo consumer |
| Delivery count | Dấu hiệu một entry bị giao lại nhiều lần |
| Group lag | Ước lượng entry chưa giao theo tiến độ group, khi khả dụng |
| Handler success/failure | Kết quả nghiệp vụ |
| ACK success/failure | Có xác nhận hoàn tất với Redis được không |
| Claim/recovery rate | Tần suất hệ thống phải cứu pending |
| DLQ size | Số entry xử lý lỗi cần điều tra |
| Handler latency p95/p99 | Đầu vào để chọn ngưỡng idle và scale |

Đặc biệt, đừng dùng `XLEN == 0` làm điều kiện duy nhất cho “đã xử lý xong”, và đừng xem `pending == 0` là “đã đọc hết Stream”.

## 18. Pending tồn đọng lâu: nhận diện consumer gặp sự cố

Giả sử:

```text
worker-A: pending 1000, idle rất lâu
worker-B: pending 2, vừa được giao
worker-C: pending 0
```

Có thể `worker-A` đã chết. Nhưng cũng có thể worker-A đang chạy một công việc dài hoặc bị kẹt ở dependency.

Quy trình hợp lý:

1. Kiểm tra sức khỏe instance và logs.
2. Xem PEL summary và chi tiết idle.
3. So sánh idle với thời gian xử lý bình thường.
4. Kiểm tra có sự kiện xử lý đang chạy với cùng message ID không.
5. Nếu đủ điều kiện, claim cho recovery worker.
6. Retry idempotent; ACK khi thành công.
7. Ghi nhận delivery count và escalation cho message lỗi nhiều lần.

Không nên “claim toàn bộ pending ngay khi thấy consumer không trả heartbeat 5 giây” nếu task có thể mất vài phút. Điều đó có thể tạo nhiều tác vụ chạy song song trên cùng một message.

## 19. Poison messages và Dead Letter Queue

**Poison message** là message mà consumer liên tục không thể xử lý được, ví dụ payload thiếu field bắt buộc, sai schema hoặc nghiệp vụ bị lỗi không thể khôi phục.

Nếu cứ claim rồi retry mãi:

```text
worker-A nhận E -> lỗi
worker-B claim E -> lỗi
worker-C claim E -> lỗi
...
```

PEL có thể tồn tại lâu, delivery count tăng và worker tiêu tốn CPU/API vô ích.

Một chính sách DLQ điển hình:

```text
Nhận message E
     |
     v
Validate / process
     |
     +-- Thành công ----------------------> XACK E
     |
     +-- Lỗi tạm thời --------------------> Chờ retry có backoff
     |
     +-- Lỗi vĩnh viễn hoặc quá retry ----> Ghi E + lý do lỗi vào DLQ
                                                |
                                                +--> Xác nhận đã lưu DLQ
                                                |
                                                +--> XACK E khỏi group gốc
```

DLQ có thể là một Redis Stream khác:

```redis
XADD orders-stream:dlq * originalId 1763000000123-0 reason INVALID_PAYLOAD
```

Ví dụ cần điền ID thực tế và payload/metadata phù hợp. Để hỗ trợ điều tra, nên lưu:

- Original stream name và original entry ID.
- Event ID nghiệp vụ.
- Payload hoặc tham chiếu payload, tránh đưa bí mật không được phép.
- Lý do lỗi, thời gian, số lần delivery.
- Version schema.
- Thông tin cần thiết để sửa rồi replay có kiểm soát.

### 19.1. Ghi DLQ rồi XACK có nguyên tử không?

Nếu DLQ và Stream nguồn nằm trên cùng Redis instance/slot, có thể thiết kế cơ chế giao dịch/script thích hợp; nhưng đừng mặc định hai lệnh độc lập:

```redis
XADD orders-stream:dlq ...
XACK orders-stream orders-workers <id>
```

là một đơn vị nguyên tử.

Có thể xảy ra:

- DLQ ghi thành công, ACK thất bại: recovery có thể tạo thêm bản DLQ nếu không idempotent.
- ACK thành công, DLQ ghi thất bại (nếu ACK trước): mất dấu vết lỗi cần xử lý.

Nếu cần đảm bảo mạnh, phải thiết kế idempotent DLQ hoặc transaction/script cùng slot khi phù hợp. Trên Redis Cluster, nhiều key khác slot không thể được cập nhật nguyên tử chỉ nhờ `MULTI`/Lua.

### 19.2. Thời điểm ACK poison message

Với lỗi không thể sửa bằng retry, ACK sau khi **bản ghi lỗi đã được lưu an toàn theo chính sách** có thể hợp lý. Nếu cứ không ACK, message sẽ bị retry vô hạn. Nhưng ACK mà không lưu dấu vết hoặc không cho phép phục hồi có thể làm nghiệp vụ mất dữ liệu.

Đây là quyết định nghiệp vụ, không phải hành vi tự động của PEL.

## 20. Retention: XACK, XDEL và XTRIM là các thao tác khác nhau

Ba nhóm thao tác:

| Lệnh | Thay đổi điều gì? | Ý nghĩa |
|---|---|---|
| `XACK` | Bỏ pending entry khỏi PEL của group | Xác nhận xử lý trong group |
| `XDEL` | Xóa entry dữ liệu khỏi Stream | Không phải ACK |
| `XTRIM` | Cắt bớt entry theo giới hạn độ dài/ID | Chính sách retention |
| `XADD ... MAXLEN` | Vừa append vừa giới hạn chiều dài log theo tùy chọn | Retention tại thời điểm ghi |
| `XGROUP DESTROY` | Xóa consumer group và trạng thái liên quan | Quản trị group, không xóa cả Stream |

Cần nhớ:

```text
ACK message != DELETE entry
DELETE entry != ACK message
```

Nếu Stream bị trim/xóa entry trước khi một group chậm ACK, PEL có thể còn ID mà payload không còn. Redis có cơ chế xử lý dangling PEL trong một số lệnh/phiên bản, nhưng điều này **không thay thế** việc thiết kế retention đúng.

### 20.1. Ví dụ XTRIM

Giữ một số lượng entry gần đúng:

```redis
XTRIM orders-stream MAXLEN ~ 100000
```

Dấu `~` cho phép trim gần đúng để tiết kiệm công xử lý, tùy cơ chế Redis. Đây chỉ là ví dụ; không nên dùng số 100.000 nếu thời gian backlog thực tế có thể vượt khả năng giữ.

Câu hỏi quan trọng:

- Consumer chậm nhất có thể mất bao lâu để xử lý hết?
- Có bao nhiêu group sử dụng Stream?
- Một message có thể pending tối đa bao lâu trước recovery?
- Nếu giữ theo MAXLEN, tốc độ ghi cực đại là bao nhiêu?
- Có cần phục vụ replay từ một mốc thời gian/ID lịch sử không?

Với nhiều group, retention cần tôn trọng **group chậm nhất** nếu dữ liệu còn cần thiết cho group đó. Cắt log chỉ dựa trên tiến độ của group nhanh nhất có thể làm mất payload mà group khác chưa xử lý.

### 20.2. Chỉ số pending không thể thay thế retention policy

Không nên nói “pending = 0 thì xóa hết Stream” nếu còn group khác, consumer mới cần lịch sử, hoặc nghĩa vụ lưu trữ dữ liệu lâu hơn. Ngược lại, giữ toàn bộ Stream vô hạn chỉ vì cần có khả năng retry có thể gây tăng RAM không kiểm soát.

Thiết kế retention và PEL recovery phải được xem là hai phần của cùng lifecycle dữ liệu.

## 21. NOACK: bỏ PEL là đánh đổi độ tin cậy

Redis hỗ trợ chế độ đọc group với tùy chọn `NOACK`:

```redis
XREADGROUP GROUP orders-workers worker-A NOACK STREAMS orders-stream >
```

Trong chế độ này, Redis không thêm các message được giao vào PEL theo cơ chế tracking thông thường. Điều này giảm overhead liên quan đến acknowledgment nhưng đồng thời **bỏ mất khả năng khôi phục bằng PEL** đối với những message ấy.

Bảng so sánh:

| Đặc điểm | XREADGROUP thường | XREADGROUP với NOACK |
|---|---|---|
| Entry mới được giao | Có | Có |
| Ghi trạng thái pending | Có | Không |
| Cần gọi XACK | Có sau xử lý thành công | Không theo cơ chế NOACK |
| Khôi phục sau crash bằng PEL | Có thể, nếu triển khai recovery | Không dựa trên PEL của message đó |
| Phù hợp nghiệp vụ bắt buộc xử lý | Thường phù hợp hơn | Thường không phù hợp |
| Overhead metadata | Có PEL | Giảm PEL overhead |

`NOACK` không biến delivery thành exactly-once; nó đơn giản từ bỏ một phần tracking. Nên chỉ dùng nếu chấp nhận mất khả năng retry sau crash, ví dụ tác vụ nhẹ có thể mất hoặc dữ liệu có thể tái tạo từ nguồn khác.

## 22. PEL ở nhiều consumer group

Một Stream có thể có hai group:

```redis
XGROUP CREATE orders-stream orders-workers 0
XGROUP CREATE orders-stream audit-workers 0
```

Hai group có tiến độ và PEL độc lập:

```text
Redis Stream orders-stream
    |
    +--> orders-workers
    |      consumer-A nhận id1
    |      XACK id1 trong orders-workers
    |
    +--> audit-workers
           audit-1 nhận id1
           id1 vẫn pending ở audit-workers
```

Gọi:

```redis
XACK orders-stream orders-workers <id1>
```

không xóa pending của `audit-workers`.

Điều này cho phép nhiều nhóm dịch vụ xử lý cùng nguồn event theo trách nhiệm khác nhau. Nhưng nó cũng tạo yêu cầu retention phức tạp: log phải được giữ đủ lâu cho mọi group cần payload.

Consumer group là cơ chế phân chia công việc **bên trong một group**; giữa các group, mỗi group có tiến độ độc lập và có thể xử lý cùng một entry.

## 23. Redis Cluster và phạm vi thao tác

Redis Streams là key Redis bình thường, nên mỗi Stream thuộc một hash slot. Các thao tác như:

```redis
XREADGROUP GROUP orders-workers worker-A STREAMS orders-stream >
XACK orders-stream orders-workers <id>
XPENDING orders-stream orders-workers
XAUTOCLAIM orders-stream orders-workers worker-B 60000 0-0
```

đều liên quan đến một Stream key trong các ví dụ này, phù hợp với định tuyến tới node sở hữu slot của key.

Tuy nhiên:

- `XREAD`/`XREADGROUP` trên nhiều Stream key khác hash slot có thể vi phạm giới hạn thao tác nhiều key của Redis Cluster.
- Transaction hay script cập nhật thêm DLQ Stream hoặc state key phải quan tâm **tất cả key có cùng hash slot hay không**.
- Không nên coi Redis Cluster có atomic transaction xuyên các primary khác nhau.
- Resharding/failover và lỗi kết nối có thể ảnh hưởng tới việc gọi ACK. Nếu không biết ACK đã thành công hay chưa, cần kiểm tra trạng thái và áp dụng idempotency thay vì retry side effect mù quáng.

Có thể thiết kế tag cùng slot khi thực sự cần atomicity của hai key:

```text
orders:{tenant-7}:stream
orders:{tenant-7}:dlq
```

Nhưng dùng tag tenant quá rộng có thể tạo hot slot. Cần cân bằng phạm vi transaction và khả năng phân phối tải.

## 24. Những tình huống lỗi thường gặp

### 24.1. “Đã xử lý rồi nhưng XPENDING vẫn còn entry”

Ứng dụng có thể chưa gọi `XACK`, gọi sai group/ID, ACK lỗi kết nối hoặc ACK chưa tới Redis. Cần kiểm tra kết quả ACK, tên Stream, group và ID Redis gốc, không dùng business ID thay thế.

### 24.2. “Tất cả message mới đều xử lý xong nhưng pending không giảm”

`XREADGROUP ... >` vẫn có thể trả message mới trong khi entry cũ tồn đọng. Cần một recovery worker quét pending và ACK có điều kiện sau xử lý.

### 24.3. “Worker mới không đọc lại message worker cũ để lại”

Đọc history với `0` chỉ trả pending của consumer name đang đọc. Dùng `XCLAIM` hoặc `XAUTOCLAIM` để chuyển ownership từ consumer cũ.

### 24.4. “Một message bị xử lý hai lần”

Có thể nghiệp vụ hoàn tất rồi consumer crash trước ACK, hoặc entry bị claim khi worker cũ còn chạy. Cần idempotency và điều chỉnh min-idle-time, không kết luận Redis Streams đã vi phạm ngữ nghĩa mà ứng dụng mong muốn.

### 24.5. “ACK làm biến mất message trong XRANGE”

`XACK` không xóa payload; nếu entry không còn trong Stream, có thể có `XDEL`, `XTRIM`, chính sách retention hoặc ứng dụng khác tác động. Cần điều tra lệnh dọn Stream.

### 24.6. “XPENDING rất cao sau khi triển khai bản mới”

Có thể handler bị lỗi serializer/schema, loader bị chậm, consumer không ACK hoặc thiếu recovery. Quan sát logs theo message ID, delivery count và oldest idle; không vội xóa PEL để làm đẹp metric.

### 24.7. “XAUTOCLAIM không trả message dù có pending”

Có thể entry chưa đủ thời gian idle, cursor chưa quét hết vùng cần xét, entry đã được consumer khác claim hoặc payload đã bị trim. Kiểm tra `XPENDING`, min-idle-time và cursor.

### 24.8. “Redis Stream tăng mãi dù pending bằng 0”

ACK không xóa Stream entry. Cần retention phù hợp với tất cả consumer group và nhu cầu replay.

### 24.9. “Chạy nhiều worker nhưng chỉ một worker có pending”

Phân phối entry mới phụ thuộc những request `XREADGROUP` đang sẵn sàng, batch size, tốc độ xử lý và consumer names. Redis không cam kết round-robin công bằng tuyệt đối trong mọi tình huống. Hãy kiểm tra polling/concurrency thay vì chỉ số PEL.

### 24.10. “Đọc với NOACK nên không thể recovery”

Đây là đặc điểm của `NOACK`, không phải lỗi PEL. Muốn có tracking và retry theo pending thì không dùng `NOACK`.

## 25. Thiết kế worker hoàn chỉnh

Một kiến trúc gợi ý:

```text
                     Redis Stream
                         |
               XREADGROUP / consumer group
                         |
         +---------------+---------------+
         |               |               |
      Worker A         Worker B        Worker C
         |               |               |
       process          process         process
         |               |               |
       XACK             XACK            XACK
                         |
                 Pending entries
                         |
                    Recovery job
                  XPENDING/XAUTOCLAIM
                         |
                 Retry idempotently
                         |
                   Success -> XACK
                   Failure -> DLQ policy
```

### 25.1. Vai trò của normal worker

- Nhận message mới (`>`).
- Validate payload/schema.
- Xử lý idempotent.
- ACK khi thành công.
- Ghi rõ lỗi và không nuốt mất thông tin.
- Có giới hạn concurrency và graceful shutdown.

### 25.2. Vai trò của recovery worker

- Quan sát pending idle.
- Claim có điều kiện với min-idle-time phù hợp.
- Xử lý lại bằng cùng logic idempotent.
- Ghi metric số lần retry và claim.
- Chuyển DLQ khi vượt chính sách retry.
- Không tạo retry storm hoặc tranh chấp với normal workers.

### 25.3. Vai trò của retention manager

- Giới hạn dữ liệu Stream theo thời gian/độ dài có cơ sở.
- Cân nhắc group chậm nhất, pending lâu nhất và nhu cầu replay.
- Tránh trim payload khi cần retry.
- Theo dõi RAM và khối lượng entry.
- Dọn consumer/group cũ theo quy trình vận hành có kiểm soát, không xóa group chỉ để giảm metric pending.

### 25.4. Vai trò của monitoring

- Báo động khi oldest pending idle vượt ngưỡng.
- Báo động khi pending tăng liên tục dù throughput ACK thấp.
- Theo dõi số message được xử lý thành công và tốc độ xuất hiện mới.
- Phân biệt lag giao message với pending chưa ACK.
- Theo dõi DLQ, lỗi ACK, lỗi claim và độ trễ handler.

## 26. Bài thực hành

### Bài 1 — Quan sát PEL trước và sau ACK

1. Tạo group bằng `XGROUP CREATE lab:orders lab-workers 0 MKSTREAM`.
2. Thêm ba message bằng `XADD`.
3. Gọi `XREADGROUP GROUP lab-workers worker-A COUNT 2 STREAMS lab:orders >`.
4. Gọi `XPENDING lab:orders lab-workers` và xem count.
5. ACK một ID đã xử lý.
6. Gọi lại `XPENDING`.
7. Dùng `XRANGE lab:orders - + COUNT 10` xác nhận entry gốc vẫn có thể còn.

Giải thích sự khác biệt giữa giảm pending và xóa entry.

### Bài 2 — Consumer crash và recovery

1. Cho `worker-A` đọc một message nhưng không ACK.
2. Ngừng worker-A.
3. Cho `worker-B` đọc bằng `XREADGROUP ... >`.
4. Giải thích vì sao worker-B không tự nhận pending của worker-A.
5. Sau khi đủ thời gian idle, gọi `XAUTOCLAIM` hoặc `XCLAIM` để chuyển ownership.
6. ACK sau khi hoàn tất.
7. Xem owner và delivery count bằng `XPENDING`.

### Bài 3 — Đọc history cùng consumer

1. Để `worker-A` có hai pending message.
2. Gọi `XREADGROUP GROUP lab-workers worker-A STREAMS lab:orders 0`.
3. So sánh với `XREADGROUP ... >`.
4. Tạo `worker-B` và gọi bằng offset `0`.
5. Giải thích sự khác nhau giữa history pending của chính consumer và group-wide pending.

### Bài 4 — Hai group độc lập

Tạo `business-group` và `audit-group` trên cùng một Stream. Cho mỗi group đọc cùng một entry bằng consumer riêng. ACK trong business-group rồi đo `XPENDING` của hai group. Giải thích vì sao ACK của một group không thay thế ACK của group kia.

### Bài 5 — Thử NOACK

Đọc một entry với `XREADGROUP ... NOACK` và xem PEL. So sánh với entry được đọc bình thường. Phân tích điều gì xảy ra nếu worker crash sau khi đã nhận message bằng NOACK.

### Bài 6 — ACK thất bại sau khi database thành công

Mô phỏng logic:

```text
Process E:
    UPDATE database
    COMMIT
    crash before XACK
```

Sau đó recovery E. Đề xuất một khóa uniqueness theo eventId trong cùng transaction database để hạn chế side effect bị áp dụng hai lần.

### Bài 7 — Poision message và DLQ

Tạo một message có payload sai định dạng. Thiết kế luồng:

```text
delivery 1 -> failed
delivery 2 -> failed
delivery 3 -> failed
write DLQ -> ACK original
```

Giải thích cách xử lý nếu ghi DLQ thành công nhưng ACK bị timeout. Cần có ID ổn định để không tạo bản lỗi trùng khi retry.

### Bài 8 — Retention và pending

Tạo group có message pending, sau đó dùng `XTRIM` trong môi trường thử nghiệm để loại bỏ payload cũ. Quan sát việc tra entry theo ID và xử lý recovery. Trả lời: Vì sao không thể dùng PEL như một bản sao payload có khả năng phục hồi sau khi Stream đã bị trim?

## 27. Câu hỏi tự đánh giá

1. Entry được thêm bằng `XADD` có vào PEL ngay không?
2. Vì sao `XREADGROUP ... >` không tự trả lại entry đã pending?
3. PEL theo dõi thông tin gì ngoài Stream ID?
4. `XPENDING` summary khác dạng range ở điểm nào?
5. `XACK` xóa dữ liệu nào và không xóa dữ liệu nào?
6. Vì sao một message đã ACK trong group A vẫn có thể pending ở group B?
7. Đọc `XREADGROUP ... 0` có lấy pending của consumer khác không?
8. Khi nào nên dùng `XCLAIM`, khi nào dùng `XAUTOCLAIM`?
9. Vì sao `min-idle-time` quá thấp có thể gây xử lý trùng?
10. Vì sao thứ tự “business commit -> ACK” vẫn cần idempotency?
11. `NOACK` thay đổi khả năng recovery ra sao?
12. Vì sao pending count bằng 0 không có nghĩa Stream rỗng?
13. Một poison message có thể ảnh hưởng throughput thế nào?
14. Nếu Stream bị trim khi PEL còn entry, recovery có thể gặp vấn đề gì?
15. Lag của group và số pending mô tả hai loại backlog khác nhau như thế nào?

## 28. Ghi nhớ

- **PEL là danh sách entry đã được consumer group giao nhưng chưa được ACK**, chứa metadata về ownership, idle time và số lần giao.
- `XADD` ghi entry vào Stream; `XREADGROUP ... >` mới giao entry mới cho group và đưa vào PEL nếu không có `NOACK`.
- **`XACK` xóa ID khỏi PEL của group, không xóa payload khỏi Stream.**
- `XPENDING` cho biết số lượng pending, owner, idle time và delivery count để giám sát và phục hồi.
- `XREADGROUP ... 0` đọc lịch sử pending của **chính consumer name**; muốn chuyển pending sang consumer khác dùng `XCLAIM` hoặc `XAUTOCLAIM`.
- Message không tự động được một consumer khác xử lý lại chỉ vì worker cũ chết; ứng dụng cần recovery worker và chính sách retry.
- **ACK sau xử lý thành công** thường an toàn hơn ACK trước, nhưng vẫn có nguy cơ duplicate nếu commit nghiệp vụ thành công và ACK thất bại.
- At-least-once thực tế cần **idempotent handler**, không thể suy ra exactly-once chỉ từ Redis Streams và PEL.
- `NOACK` bỏ tracking pending, đánh đổi khả năng recovery.
- Retention của Stream phải được thiết kế cùng PEL và group chậm nhất; `XTRIM` hoặc `XDEL` không thay thế `XACK`.
- Poision message cần retry có giới hạn, DLQ, logs và escalation thay vì lặp vô hạn.
- Trong Spring Data Redis, `StreamOperations`/listener container hỗ trợ đọc Stream; thời điểm ACK phải phù hợp ranh giới hoàn tất nghiệp vụ.

### Tài liệu tham khảo chính thức

- [Redis — Introduction to Streams](https://redis.io/docs/latest/develop/data-types/streams/)
- [Redis — XREADGROUP](https://redis.io/docs/latest/commands/xreadgroup/)
- [Redis — XPENDING](https://redis.io/docs/latest/commands/xpending/)
- [Redis — XACK](https://redis.io/docs/latest/commands/xack/)
- [Redis — XCLAIM](https://redis.io/docs/latest/commands/xclaim/)
- [Redis — XAUTOCLAIM](https://redis.io/docs/latest/commands/xautoclaim/)
- [Redis — XGROUP CREATE](https://redis.io/docs/latest/commands/xgroup-create/)
- [Redis — XINFO GROUPS](https://redis.io/docs/latest/commands/xinfo-groups/)
- [Redis — XTRIM](https://redis.io/docs/latest/commands/xtrim/)
- [Spring Data Redis — Redis Streams](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html)
- [Spring Data Redis — Stream Processing](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html)
