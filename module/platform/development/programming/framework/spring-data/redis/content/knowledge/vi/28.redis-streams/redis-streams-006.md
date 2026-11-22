# Phân biệt xác nhận xử lý với xóa bản ghi khỏi Stream

## 1. Cùng một thông điệp nhưng có hai vòng đời khác nhau

Giả sử ứng dụng Spring Boot dùng **Spring Data Redis Streams** để xử lý sự kiện đơn hàng. Khi người dùng thanh toán, dịch vụ phát bản ghi:

```redis
XADD orders:events * eventType order.paid orderId O-42
```

Một consumer thuộc group `billing` đọc sự kiện và ghi nhận thanh toán. Sau đó ứng dụng cần quyết định:

- Đã xử lý thành công thì **xác nhận** với Redis bằng `XACK`?
- Hay phải **xóa bản ghi** khỏi Stream bằng `XDEL`?
- Có cần cả hai không, và nếu dùng cả hai thì thứ tự có quan trọng không?

Điểm cốt lõi là **xác nhận xử lý và xóa dữ liệu là hai hành động độc lập**:

- **`XACK`** xác nhận một bản ghi đã được xử lý trong **một consumer group cụ thể**. Nó loại tham chiếu tới bản ghi đó khỏi **Pending Entries List (PEL)** của group ấy. **Bản ghi gốc vẫn nằm trong Stream**.
- **`XDEL`** xóa nội dung bản ghi khỏi **Stream**. Thao tác này ảnh hưởng tới dữ liệu chung mà các consumer group đều có thể cần. **Nó không tương đương với việc `XACK` cho mọi group**, và trong cơ chế truyền thống các tham chiếu tới ID bị xóa có thể vẫn tồn tại trong PEL.

```text
                          Redis Stream
                    orders:events (bản ghi gốc)
                    +-------------------------+
                    | 1700000000000-0         |
                    | orderId=O-42            |
                    +------------+------------+
                                 |
                   +-------------+--------------+
                   |                            |
                   v                            v
           Consumer group A              Consumer group B
             "billing"                      "analytics"
                   |                            |
           Pending Entries List          Pending Entries List
                   |                            |
         XACK trong group A              Chưa xử lý xong
                   |                            |
              PEL A: đã gỡ              PEL B: có thể còn
                   |
                   +--- Bản ghi vẫn ở Redis Stream ---+

XDEL xóa bản ghi gốc trong Stream, không chỉ đánh dấu riêng group A.
```

**Nguyên tắc vận hành:** consumer nên `XACK` **sau khi xử lý nghiệp vụ thành công**; việc xóa hoặc trim Stream là **chính sách lưu giữ dữ liệu** riêng, cần xét tất cả consumer group và nhu cầu đọc lại.

Bài học này thuộc chương **Redis Streams** của Spring Data Redis, tập trung vào cách phân biệt hai khái niệm, quy trình xử lý thông điệp, các tình huống lỗi và việc quản lý dữ liệu khi một Stream có nhiều nhóm consumer.

## 2. Hiểu cấu trúc Redis Stream và Consumer Group

### 2.1. Stream chứa bản ghi có ID

Redis Stream là cấu trúc dữ liệu gồm các entry theo thứ tự ID. Mỗi entry có một ID và các trường giá trị.

Ví dụ:

```redis
XADD orders:events * type order.paid orderId O-42 amount 250000
```

Redis trả về một ID, ví dụ:

```text
"1700000000000-0"
```

ID thực tế do Redis cấp có thể khác. Để xem bản ghi trong Stream:

```redis
XRANGE orders:events - +
```

Để đếm số bản ghi hiện còn trong Stream:

```redis
XLEN orders:events
```

`XRANGE` đọc dữ liệu gốc của Stream, còn `XLEN` đo số entry hiện được giữ lại. Cả hai thao tác này **không cho biết riêng một consumer group đã xử lý xong những gì**.

### 2.2. Consumer group theo dõi việc phân phối

Có thể tạo consumer group:

```redis
XGROUP CREATE orders:events billing 0 MKSTREAM
```

Lệnh này tạo group `billing`. `MKSTREAM` cho phép tạo Stream rỗng nếu chưa tồn tại; vị trí bắt đầu `0` cho phép group đọc các entry cũ nếu có. Nếu dùng `$` khi tạo group, group thường bắt đầu từ cuối Stream và chỉ nhận những entry thêm sau đó.

Một consumer lấy thông điệp mới:

```redis
XREADGROUP GROUP billing billing-1 COUNT 1 STREAMS orders:events >
```

Dấu `>` yêu cầu những thông điệp chưa từng được phân phối cho group. Khi một entry được giao theo cơ chế consumer group, Redis ghi nhận nó trong **Pending Entries List (PEL)** cho tới lúc được xác nhận hoặc được xử lý bằng cơ chế liên quan.

### 2.3. PEL lưu trạng thái cần xác nhận, không phải bản sao toàn bộ payload

PEL chứa các thông tin quản lý việc phân phối như:

- ID của bản ghi đang chờ xác nhận.
- Consumer đang sở hữu việc xử lý.
- Khoảng thời gian từ lần được giao gần nhất (*idle time*).
- Số lần đã được giao lại (*delivery count*).

Bản thân nội dung field/value của entry nằm trong Stream. PEL không phải một bản sao hoàn chỉnh để khôi phục nội dung đã bị xóa khỏi Stream.

Hai nguồn thông tin khác nhau:

| Câu hỏi | Nguồn kiểm tra |
|---|---|
| Entry có còn trong Stream không? | `XRANGE`, `XREVRANGE`, `XLEN` |
| Group nào đã nhận nhưng chưa xác nhận? | `XPENDING`, `XINFO GROUPS` |
| Consumer nào đang sở hữu pending ID? | `XPENDING` dạng chi tiết, `XINFO CONSUMERS` |
| Một ID đã được group hiện tại xác nhận chưa? | PEL của group không còn ID sau `XACK` thành công |
| Đã xử lý nghiệp vụ trong database chưa? | Trạng thái nghiệp vụ/idempotency ở hệ thống có thẩm quyền |

**Có trong Stream** và **còn pending** là hai điều kiện hoàn toàn khác nhau.

## 3. XACK thực sự làm gì?

Cú pháp Redis:

```redis
XACK key group id [id ...]
```

Ví dụ:

```redis
XACK orders:events billing 1700000000000-0
```

Ý nghĩa: trong consumer group `billing`, đánh dấu ID trên đã được xác nhận xử lý bằng cách loại ID khỏi PEL của group đó.

Nếu một ID đang pending và được xác nhận thành công, lệnh thường trả:

```text
(integer) 1
```

Nếu ID không có trong PEL của group hoặc đã được xác nhận trước đó, kết quả có thể là `0`. Điều này **không tự chứng minh bản ghi đã bị xóa khỏi Stream**.

### 3.1. Sau XACK, bản ghi vẫn ở Stream

Ví dụ:

```redis
XACK orders:events billing 1700000000000-0
XRANGE orders:events - +
XLEN orders:events
```

Sau `XACK`, `XRANGE` vẫn có thể hiển thị bản ghi đã xử lý và `XLEN` không giảm chỉ vì lệnh ACK.

Lý do: Stream là nơi giữ lịch sử entry; consumer group là một lớp trạng thái quản lý phân phối. `XACK` thao tác lên **PEL của group**, không phải lên nội dung Stream.

### 3.2. Sau XACK, entry không còn pending trong group đó

Kiểm tra:

```redis
XPENDING orders:events billing
```

Khi mọi entry đã được ACK, phần tổng số pending của group có thể về `0`.

Điều này có ích vì:

- Redis không còn xem entry là công việc chưa được xác nhận của group.
- Consumer khác không cần reclaim entry đó như công việc đang dở của group.
- Thông tin PEL liên quan được giải phóng.
- Hệ thống có thể phân biệt công việc đã xác nhận với công việc cần retry.

### 3.3. XACK không có nghĩa “xử lý đúng một lần”

Một thông điệp có thể được xử lý thành công nhưng chương trình chết **trước khi gửi XACK**:

```text
Consumer đọc entry
        |
        v
Ghi database thành công
        |
        v
Ứng dụng bị dừng
        |
        XACK chưa được gửi
        |
        v
Entry vẫn pending và có thể được giao lại
```

Khi thông điệp được xử lý lại, nếu không có cơ chế chống lặp, tác dụng nghiệp vụ có thể được thực hiện hai lần.

`XACK` là xác nhận ở mức **consumer group**, không phải giao dịch nguyên tử giữa Redis và database, HTTP API hoặc hệ thống thanh toán.

## 4. XDEL thực sự làm gì?

Cú pháp Redis:

```redis
XDEL key id [id ...]
```

Ví dụ:

```redis
XDEL orders:events 1700000000000-0
```

Lệnh này xóa **entry có ID được chỉ định** khỏi nội dung Stream. Nếu entry đang tồn tại, Redis có thể trả số entry đã xóa là `1`.

Sau khi xóa:

```redis
XRANGE orders:events - +
XLEN orders:events
```

`XRANGE` không còn hiển thị entry đã xóa và `XLEN` giảm theo số entry thực sự bị loại khỏi Stream.

### 4.1. XDEL không phải XACK

`XDEL` không có tham số consumer group:

```text
XACK orders:events billing <ID>
                    ^^^^^^^
               Group cần xác nhận

XDEL orders:events <ID>
       Không có tên group
```

Vì vậy, `XDEL` không thể mang ý nghĩa “đã xử lý xong trong group billing”. Nó thao tác lên bản ghi chung của Stream, không phải riêng trạng thái xác nhận của một group.

Trong các cơ chế Stream truyền thống, nếu một ID đã được giao và vẫn còn pending, **xóa entry bằng XDEL không tự động dọn mọi tham chiếu tới ID ấy trong PEL**. Điều này tạo tình trạng PEL chứa tham chiếu tới bản ghi không còn payload.

### 4.2. Điều gì xảy ra nếu XDEL trước XACK?

Giả sử:

```text
Stream:    entry E còn tồn tại
PEL A:     E đang pending
```

Một tiến trình khác gọi:

```redis
XDEL orders:events <E>
```

Trạng thái có thể trở thành:

```text
Stream:    không còn entry E
PEL A:     vẫn còn tham chiếu E
```

Khi consumer thử đọc lại pending của chính mình, nó có thể nhìn thấy ID nhưng không lấy được field/value gốc. Redis 7.0 trở lên có khả năng dọn những tham chiếu PEL tới entry đã bị xóa trong một số quá trình reclaim như `XAUTOCLAIM`, nhưng điều đó **không đồng nghĩa XDEL tự ACK và dọn mọi pending**.

Nếu công việc yêu cầu nội dung message để retry, xóa payload trước khi mọi consumer cần thiết hoàn thành là một rủi ro mất khả năng xử lý lại.

### 4.3. XDEL có xóa cả Stream key không?

Không nên nhầm **xóa một entry** với **xóa key Stream**:

```redis
XDEL orders:events <ID>
```

chỉ nhắm tới entry có ID đó.

Trong khi:

```redis
DEL orders:events
```

xóa **toàn bộ key Stream** cùng dữ liệu và metadata liên quan. Đây là hành động rất khác, có thể làm mất toàn bộ lịch sử và consumer group của Stream.

## 5. Bảng đối chiếu XACK và XDEL

| Tiêu chí | `XACK` | `XDEL` |
|---|---|---|
| Mục đích | Xác nhận xử lý trong consumer group | Xóa entry khỏi Stream |
| Cú pháp | `XACK stream group id` | `XDEL stream id` |
| Cần tên group? | **Có** | Không |
| Ảnh hưởng PEL group được chỉ định | Xóa pending reference được ACK | Không phải thao tác ACK |
| Ảnh hưởng payload của entry | **Giữ nguyên** | **Loại khỏi Stream** |
| Ảnh hưởng group khác | Không ACK giúp group khác | Group khác có thể mất payload cần xử lý |
| `XRANGE` sau thao tác | Vẫn có thể xem entry | Không còn entry bị xóa |
| `XLEN` sau thao tác | Không giảm vì ACK | Có thể giảm |
| `XPENDING` group xử lý | Giảm khi ACK thành công | Pending reference có thể còn |
| Dùng lúc nào? | **Sau xử lý nghiệp vụ thành công** | Khi chính sách lưu giữ cho phép xóa |
| Có phải giải pháp chống lặp toàn diện? | Không | Không |
| Có tạo transaction với SQL? | Không | Không |

**Tóm lại:** `XACK` trả lời “group này còn phải retry entry không?”; `XDEL` trả lời “entry này còn nằm trong dữ liệu Stream không?”.

## 6. Thực hành Redis CLI: ACK mà không xóa entry

Thực hiện trên một Redis dành cho phát triển. Dùng namespace riêng để tránh ảnh hưởng dữ liệu thật.

### Bước 1: Tạo group

```redis
XGROUP CREATE demo:orders:events demo-billing 0 MKSTREAM
```

Lệnh trên được thực hiện một lần khi group chưa tồn tại. Nếu chạy lại sẽ nhận lỗi `BUSYGROUP`; đây là dấu hiệu group đã được tạo, không nên tự động xóa/khởi tạo lại group khi gặp lỗi này.

### Bước 2: Thêm entry

```redis
XADD demo:orders:events * type order.paid orderId O-42 amount 250000
```

Giả sử Redis trả ID:

```text
1700000000000-0
```

Trong các lệnh tiếp theo, **thay `<ID>` bằng ID thực sự mà XADD trả về**. Dãy số trên chỉ để minh họa.

### Bước 3: Consumer đọc thông điệp mới

```redis
XREADGROUP GROUP demo-billing bill-1 COUNT 1 STREAMS demo:orders:events >
```

Redis trả thông điệp và ID. Bởi vì thông điệp đã được giao qua consumer group, nó trở thành pending khi chưa được xác nhận.

### Bước 4: Kiểm tra PEL

```redis
XPENDING demo:orders:events demo-billing
```

Kết quả có thể thể hiện 1 pending entry. Muốn xem chi tiết một khoảng ID:

```redis
XPENDING demo:orders:events demo-billing - + 10
```

Kết quả bao gồm ID, consumer chủ sở hữu, idle time và delivery count.

### Bước 5: XACK sau khi đã xử lý thành công

```redis
XACK demo:orders:events demo-billing <ID>
```

Nếu ID đang pending, kết quả thường là `1`.

### Bước 6: Đối chiếu trạng thái

```redis
XPENDING demo:orders:events demo-billing
XRANGE demo:orders:events - +
XLEN demo:orders:events
```

Điều cần quan sát:

- Tổng pending trong `demo-billing` giảm về 0 nếu không có entry khác.
- Bản ghi `<ID>` vẫn xuất hiện khi `XRANGE`.
- `XLEN` vẫn tính entry đó.

Như vậy có thể tự chứng minh **ACK không xóa bản ghi khỏi Stream**.

### Bước 7: Xóa dữ liệu gốc có chủ đích

Chỉ trong môi trường thực hành, sau khi đã quan sát đủ:

```redis
XDEL demo:orders:events <ID>
XRANGE demo:orders:events - +
XLEN demo:orders:events
```

Bây giờ bản ghi `<ID>` không còn được hiển thị. Hành động này khác với `XACK` ở bước 5.

## 7. Nhiều consumer group cùng cần một entry

Một Stream có thể phục vụ các nhóm độc lập:

```text
                      orders:events
                      +-----------+
                      | Event E   |
                      +-----+-----+
                            |
                +-----------+------------+
                |                        |
                v                        v
           Group billing             Group analytics
           Ghi thanh toán           Tổng hợp báo cáo
                |                        |
                v                        v
             XACK E                 Chưa đọc E
                |                        |
            PEL billing = 0          Chưa xử lý xong
                |
                +------- Entry E vẫn cần cho analytics
```

`XACK` trong group `billing` **không xác nhận cho** group `analytics`. Mỗi group có tiến độ phân phối và PEL riêng.

### 7.1. Tạo hai group và đọc độc lập

Ví dụ Redis CLI:

```redis
XGROUP CREATE demo:multi:orders billing 0 MKSTREAM
XGROUP CREATE demo:multi:orders analytics 0

XADD demo:multi:orders * type order.paid orderId O-42
```

Lưu lại ID được `XADD` trả về.

Consumer của `billing` đọc:

```redis
XREADGROUP GROUP billing bill-1 COUNT 1 STREAMS demo:multi:orders >
```

Consumer của `analytics` cũng có thể đọc cùng entry:

```redis
XREADGROUP GROUP analytics analytics-1 COUNT 1 STREAMS demo:multi:orders >
```

Group billing hoàn thành trước:

```redis
XACK demo:multi:orders billing <ID>
XPENDING demo:multi:orders billing
XPENDING demo:multi:orders analytics
```

Trạng thái dự kiến: pending của billing đã được gỡ, còn analytics vẫn pending vì chưa ACK.

Nếu lúc này gọi:

```redis
XDEL demo:multi:orders <ID>
```

thì payload gốc bị xóa, dù analytics vẫn cần dữ liệu để xử lý hoặc retry. Đây là ví dụ điển hình cho việc **xóa dữ liệu quá sớm**.

### 7.2. Quy tắc khi có nhiều group

Không nên để một consumer group tùy ý xóa entry ngay sau khi nó xử lý xong nếu:

- Các group khác cũng đọc Stream đó.
- Có group tạm offline hoặc xử lý chậm.
- Cần giữ dữ liệu để kiểm toán hoặc xử lý lại.
- Stream có SLA lưu giữ trong một khoảng thời gian.

Trong thiết kế thực tế, thường **mỗi consumer chỉ phụ trách XACK của group mình**. Một thành phần quản lý retention riêng sẽ quyết định lúc nào có thể trim/xóa entry theo chính sách toàn Stream.

## 8. Xử lý thành công, thất bại và thời điểm ACK

### 8.1. Trình tự được khuyến nghị

Một worker nhận sự kiện thanh toán:

```text
XREADGROUP
     |
     v
Nhận entry E, Redis đưa E vào PEL
     |
     v
Kiểm tra và xử lý nghiệp vụ
     |
     +---- Lỗi xử lý ----> Không ACK
     |                       |
     |                       v
     |                   E vẫn pending
     |                   để retry/reclaim
     |
     v
Ghi nhận nghiệp vụ thành công
     |
     v
XACK E cho group hiện tại
     |
     v
Kết thúc xử lý
```

**Chỉ ACK sau khi tác dụng phụ cần thiết đã hoàn thành** theo ranh giới nghiệp vụ. Nếu yêu cầu là ghi database, cần xét việc transaction database đã commit hay chưa.

### 8.2. ACK trước khi xử lý là nguy hiểm

Nếu code làm như sau:

```text
XREADGROUP -> XACK -> gọi PaymentService -> PaymentService lỗi
```

thì entry đã rời PEL. Redis không còn quản lý entry đó như một công việc pending của group, và cơ chế retry thông thường dựa trên PEL sẽ không tự lấy lại nó. Payload có thể vẫn còn trong Stream, nhưng ứng dụng phải có quy trình phục hồi riêng để phát hiện và xử lý.

Do đó, không nên dùng **auto-ack khi vừa nhận** nếu tác vụ có thể thất bại và phải retry dựa trên PEL.

### 8.3. Xử lý thành công nhưng chưa ACK

Trường hợp ngược lại:

```text
XREADGROUP -> ghi database thành công -> crash trước XACK
```

Redis vẫn giữ entry trong PEL. Sau khi phục hồi, entry có thể được xử lý lại.

Đây là lý do worker cần **idempotency**, chẳng hạn lưu `eventId` đã xử lý trong database với ràng buộc duy nhất và thực hiện tác dụng nghiệp vụ trong cùng transaction.

### 8.4. Các cửa sổ lỗi điển hình

| Thời điểm lỗi | Trạng thái Redis có thể thấy | Hướng xử lý |
|---|---|---|
| Crash trước khi nhận entry | Entry chưa giao cho group | Consumer khác có thể đọc thông điệp mới |
| Crash sau `XREADGROUP`, trước nghiệp vụ | Pending | Reclaim/retry khi đủ điều kiện |
| Nghiệp vụ lỗi | Pending nếu chưa ACK | Retry có giới hạn hoặc xử lý lỗi |
| Database commit xong, crash trước ACK | Pending dù tác dụng đã thành công | Retry **idempotent** rồi ACK |
| ACK thành công nhưng ứng dụng không nhận phản hồi | PEL có thể đã được gỡ | Phải xác minh; không giả định chắc chắn ACK thất bại |
| `XDEL` trước khi consumer khác xử lý | Payload không còn | Có nguy cơ mất khả năng xử lý lại |
| Trim xóa entry còn pending | PEL có thể còn tham chiếu | Phải có quy trình xử lý dangling reference |

**Không có thao tác XACK riêng lẻ nào bảo đảm “exactly once” xuyên Redis và một hệ thống dữ liệu khác.** Tính đúng một lần ở mức tác dụng nghiệp vụ cần được xây từ giao dịch và cơ chế idempotency phù hợp.

## 9. Pending Entries List và khôi phục consumer lỗi

### 9.1. XPENDING: biết điều gì đang chờ

Một lần đọc qua consumer group làm entry xuất hiện trong PEL cho tới khi ACK. Kiểm tra:

```redis
XPENDING orders:events billing
```

Muốn xem chi tiết:

```redis
XPENDING orders:events billing - + 20
```

Các thông tin hữu ích:

- Tổng số entry pending.
- Khoảng ID có entry pending.
- Consumer đang giữ các entry pending.
- Thời gian nhàn rỗi và số lần delivery.

Không nên coi “pending = 0” là Stream rỗng. Nó chỉ mô tả trạng thái xác nhận của **group được hỏi**.

### 9.2. Đọc lại pending của chính consumer

Consumer dùng dấu `>` để lấy **entry mới chưa được giao cho group**:

```redis
XREADGROUP GROUP billing bill-1 COUNT 10 STREAMS orders:events >
```

Để đọc **pending history của chính consumer đó**, có thể dùng một ID cụ thể như `0`:

```redis
XREADGROUP GROUP billing bill-1 COUNT 10 STREAMS orders:events 0
```

Hai lựa chọn khác nhau:

- `>`: luồng nhận công việc mới.
- `0`: xem các entry pending đã từng giao cho **consumer đó** theo vị trí đọc phù hợp.

Dùng `>` liên tục **không tự lấy lại toàn bộ pending cũ**. Tính chất này rất quan trọng khi thiết kế worker khởi động lại sau sự cố.

### 9.3. XCLAIM và XAUTOCLAIM

Nếu consumer `bill-1` đã chết nhưng còn nắm nhiều entry pending, một consumer khác có thể lấy quyền xử lý bằng cơ chế claim, chẳng hạn:

```redis
XAUTOCLAIM orders:events billing bill-2 60000 0-0 COUNT 10
```

Ví dụ này tìm các pending entry có idle time đủ 60 giây rồi chuyển quyền sở hữu sang `bill-2`, theo cơ chế của `XAUTOCLAIM`.

Sau khi được claim, `bill-2` xử lý lại nghiệp vụ, kiểm tra idempotency và **XACK** khi hoàn tất. Không dùng `XDEL` để “giải quyết nhanh” một entry đang pending vì có thể làm mất payload mà worker cần để retry.

Các điều cần thiết kế:

- Ngưỡng `min-idle-time` phải phù hợp thời gian xử lý bình thường.
- Retry có giới hạn số lần hoặc có chính sách đưa sang luồng lỗi.
- Nếu có xử lý song song, nhiều worker không nên cùng thực hiện tác dụng phụ không idempotent.
- Theo dõi pending tồn lâu và số lần delivery.
- Khi reclaim entry đã bị xóa payload, phải xử lý tình huống **không còn nội dung**; trong Redis 7.0 trở lên, `XAUTOCLAIM` còn có cơ chế dọn một số tham chiếu dangling PEL khi gặp entry đã bị xóa.

### 9.4. Vì sao XDEL không phải công cụ giải quyết pending?

Một pending entry biểu thị “group đã nhận nhưng chưa xác nhận”. Muốn kết thúc trách nhiệm xử lý của group thì:

1. Thực hiện nghiệp vụ hoặc xử lý thất bại theo chính sách.
2. Chỉ khi đủ điều kiện, gọi `XACK` (hoặc cơ chế ACK tương đương).

`XDEL` chỉ xóa payload chung, không xác minh tác dụng nghiệp vụ đã thành công. Vì vậy, `XDEL` không phải lệnh thay cho ACK hoặc retry.

## 10. Spring Data Redis: ACK và DELETE là hai API khác nhau

Spring Data Redis cung cấp `StreamOperations` qua `RedisTemplate.opsForStream()`.

### 10.1. ACK một record

Trong Spring Data Redis, có thể gọi:

```java
import org.springframework.data.redis.connection.stream.RecordId;
import org.springframework.data.redis.core.StringRedisTemplate;

public class StreamAckExample {

    private final StringRedisTemplate redis;

    public StreamAckExample(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Long acknowledge(String recordId) {
        return redis.opsForStream().acknowledge(
                "orders:events",
                "billing",
                RecordId.of(recordId)
        );
    }
}
```

Hành vi tương đương về ý nghĩa với:

```redis
XACK orders:events billing <ID>
```

Phương thức `acknowledge(...)` nhận tên group vì ACK thuộc về **một consumer group**.

Nếu `Long` kết quả là `1`, một pending reference tương ứng đã được ACK. Trả về `0` có thể do ID không còn trong PEL hoặc đã được ACK từ trước; không được suy ra payload đã bị xóa.

### 10.2. Xóa record khỏi Stream

Spring Data Redis cũng có thao tác `delete(...)` trên `StreamOperations`:

```java
public Long deleteFromStream(String recordId) {
    return redis.opsForStream().delete(
            "orders:events",
            RecordId.of(recordId)
    );
}
```

Nó tương ứng về ý nghĩa với:

```redis
XDEL orders:events <ID>
```

Không có tên group vì đây là thay đổi **dữ liệu Stream dùng chung**.

Hai phương thức Java có kiểu kết quả gần giống nhau nhưng **không có cùng tác dụng**. Đừng gộp `acknowledge(...)` và `delete(...)` vào một phương thức `complete(...)` không phân biệt chính sách xử lý với chính sách lưu giữ.

### 10.3. Một listener chỉ ACK sau khi xử lý thành công

Ví dụ Spring Data Redis với `StreamListener`:

```java
package com.example.redis.stream;

import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.stream.StreamListener;
import org.springframework.stereotype.Component;

@Component
public class BillingStreamListener
        implements StreamListener<String, MapRecord<String, String, String>> {

    private static final String STREAM = "orders:events";
    private static final String GROUP = "billing";

    private final StringRedisTemplate redis;
    private final BillingProcessor processor;

    public BillingStreamListener(
            StringRedisTemplate redis,
            BillingProcessor processor) {
        this.redis = redis;
        this.processor = processor;
    }

    @Override
    public void onMessage(MapRecord<String, String, String> record) {

        // Thành phần nghiệp vụ phải dùng ID sự kiện hoặc khóa
        // nghiệp vụ để xử lý lặp lại một cách an toàn.
        processor.processIdempotently(
                record.getId().getValue(),
                record.getValue()
        );

        // Chỉ chạy đến đây nếu processor không ném lỗi
        // và phần nghiệp vụ cần thiết đã hoàn tất.
        redis.opsForStream().acknowledge(
                STREAM,
                GROUP,
                record.getId()
        );

        // KHÔNG xóa entry khỏi Stream ở đây theo mặc định.
        // Chính sách retention được xử lý riêng.
    }
}
```

Ở đây `BillingProcessor` là một service do ứng dụng cung cấp, chịu trách nhiệm xử lý nghiệp vụ và chống lặp:

```java
package com.example.redis.stream;

import java.util.Map;

public interface BillingProcessor {

    void processIdempotently(
            String streamEntryId,
            Map<String, String> fields
    );
}
```

Trong hệ thống thực, một phương thức nghiệp vụ thường dùng transaction database và ràng buộc duy nhất theo `streamEntryId` hoặc `eventId` để tránh ghi hiệu ứng hai lần khi record được giao lại.

**Ý tưởng chính:** không `XACK` trong nhánh thất bại. Lưu ý exception trong listener có thể ảnh hưởng subscription/container; cấu hình retry, reclaim và error handler phải được thiết kế riêng.

### 10.4. Cấu hình container nhận message theo consumer group

Spring Data Redis có `StreamMessageListenerContainer` cho việc nhận message theo mô hình imperative:

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
public class BillingStreamConfiguration {

    @Bean
    public StreamMessageListenerContainer<
            String, MapRecord<String, String, String>>
    billingStreamContainer(
            RedisConnectionFactory connectionFactory,
            BillingStreamListener listener) {

        var options = StreamMessageListenerContainer
                .StreamMessageListenerContainerOptions
                .<String, MapRecord<String, String, String>>builder()
                .pollTimeout(Duration.ofSeconds(1))
                .build();

        var container = StreamMessageListenerContainer.create(
                connectionFactory,
                options
        );

        container.receive(
                Consumer.from("billing", "billing-1"),
                StreamOffset.create(
                        "orders:events",
                        ReadOffset.lastConsumed()
                ),
                listener
        );

        return container;
    }
}
```

Ví dụ giả định group `billing` **đã tồn tại** trước khi consumer bắt đầu, chẳng hạn được tạo bằng `XGROUP CREATE`. Không nên xóa và tạo lại group ở mỗi lần ứng dụng khởi động vì có thể làm mất metadata tiến độ phân phối.

`StreamMessageListenerContainer` được Spring quản lý vòng đời. Với lựa chọn `receive(...)`, record **cần ACK thủ công** sau xử lý. Nếu dùng `receiveAutoAck(...)`, record được xác nhận khi nhận; đó **không phải** chính sách an toàn mặc định cho công việc cần retry sau khi handler thất bại.

Tùy phiên bản Spring Data Redis, tên lớp và builder generic có thể khác đôi chút; cần dùng API của phiên bản đã chọn. Các API cốt lõi `opsForStream().acknowledge(...)`, `opsForStream().delete(...)`, `StreamListener` và `StreamMessageListenerContainer` là trọng tâm của ví dụ.

## 11. Lưu ý về kết quả ACK, lỗi mạng và idempotency

Giả sử ứng dụng xử lý thành công rồi gửi `XACK`. Kết quả của `acknowledge(...)` có thể bị ảnh hưởng bởi lỗi mạng:

```text
Ứng dụng                        Redis
    |                             |
    | XACK E --------------------> |
    |                             | XACK thành công
    |                             |
    |     [Mất kết nối trước khi ứng dụng nhận phản hồi]
    |
    | Không biết chắc ACK đã thành công hay chưa
```

Trong trường hợp này, không nên tự suy luận:

- “Có exception, chắc chắn Redis chưa ACK”.
- “XACK trả 0, chắc chắn nghiệp vụ chưa chạy”.
- “PEL trống, chắc chắn database đã commit”.

Phải tách **trạng thái ACK của group** khỏi **trạng thái nghiệp vụ**. Nếu cần đối chiếu, đọc PEL, trạng thái database và bản ghi idempotency của chính ứng dụng.

### 11.1. Một mẫu chống xử lý lặp

Giả sử mỗi sự kiện có ID bất biến `eventId`, hoặc dùng ID entry của Stream như một định danh xử lý. Trong database có thể lưu một bảng:

```text
processed_events
  event_id (UNIQUE)
  processed_at
```

Tại thời điểm xử lý:

1. Bắt đầu database transaction.
2. Thử ghi `event_id` vào bảng với ràng buộc duy nhất.
3. Nếu đã tồn tại, coi tác dụng nghiệp vụ trước đó đã hoàn thành theo chính sách.
4. Nếu chưa tồn tại, thực hiện thao tác nghiệp vụ và ghi dấu đã xử lý trong cùng transaction.
5. Commit transaction.
6. Gọi `XACK` cho entry của group hiện tại.

Nếu ứng dụng chết sau bước 5 và trước bước 6, entry vẫn pending, nhưng lượt xử lý lại phát hiện `event_id` đã có và không tạo tác dụng lặp. Sau đó consumer có thể ACK.

Đây là **mẫu thiết kế**, không phải tính năng “exactly once” tự động của Redis Streams. Việc áp dụng vào nhiều cơ sở dữ liệu hoặc dịch vụ bên ngoài còn đòi hỏi cơ chế idempotency riêng cho từng tác dụng phụ.

## 12. Xóa theo chính sách lưu giữ, không theo cảm tính của từng worker

### 12.1. Vì sao cần retention?

Nếu mọi entry chỉ được `XACK` mà không có cơ chế xóa/trim, Stream tiếp tục giữ dữ liệu đã xử lý. Kích thước có thể tăng theo thời gian:

```text
Ngày 1:      100.000 entries
Ngày 7:      700.000 entries
Ngày 30:   3.000.000 entries
```

Redis tiêu thụ bộ nhớ và việc giữ lịch sử vô thời hạn thường không cần thiết cho mọi ứng dụng.

Vì vậy, ứng dụng nên có một **chính sách lưu giữ**: giữ tối đa bao nhiêu entry, bao lâu, hoặc chỉ xóa sau khi các group bắt buộc đã xử lý.

### 12.2. XTRIM dùng để giới hạn Stream

Ví dụ:

```redis
XTRIM orders:events MAXLEN ~ 100000
```

Lệnh này yêu cầu giữ kích thước Stream gần mức 100.000 entry; dấu `~` cho phép trim xấp xỉ để tối ưu cách Redis lưu dữ liệu.

Có thể áp dụng giới hạn khi thêm entry:

```redis
XADD orders:events MAXLEN ~ 100000 * type order.paid orderId O-42
```

Cần nhớ:

- `MAXLEN` là giới hạn **số entry**, không phải tổng byte.
- `~` là xấp xỉ; số entry thật có thể cao hơn ngưỡng một thời gian.
- Trim/xóa có thể làm mất payload mà consumer chậm chưa xử lý.
- Redis **không tự hiểu** rằng một entry đã được mọi group xử lý chỉ vì nó đủ cũ hoặc vượt ngưỡng số lượng.

Trên các phiên bản Redis truyền thống, cơ chế trim như `XTRIM` mặc định có thể giữ tham chiếu PEL tới entry đã xóa. Do đó, retention phải được thiết kế cùng với chính sách xử lý pending và số group.

### 12.3. Không xóa ngay sau ACK nếu còn group khác

Trình tự không an toàn:

```text
Billing: XREADGROUP -> xử lý -> XACK -> XDEL ngay
Analytics: chưa đọc / còn pending -> mất payload
```

Một lựa chọn an toàn hơn:

```text
Billing:   XREADGROUP -> xử lý -> XACK
Analytics: XREADGROUP -> xử lý -> XACK
Retention: kiểm tra điều kiện xóa chung -> xóa/trim theo chính sách
```

Việc “kiểm tra đủ điều kiện” có thể dựa trên:

- Tiến độ các group quan trọng.
- Mốc thời gian hoặc ID retention.
- Thời hạn giữ lịch sử phục vụ điều tra.
- Chính sách pháp lý/vận hành.
- Cơ chế xóa có hiểu trạng thái ACK của mọi group khi phiên bản Redis hỗ trợ.

Lưu ý: chỉ kiểm tra `XPENDING = 0` chưa chắc đủ để xác nhận **tất cả entry cũ đã được đọc**, vì một group có thể chưa nhận entry nào nên không có pending. Cần quan tâm cả tiến độ giao hàng/ACK và điều kiện lưu giữ.

## 13. Redis 8.2 trở lên: XACKDEL, XDELEX và các chế độ tham chiếu

Từ **Redis 8.2**, các lệnh Streams có thêm lựa chọn xử lý mối quan hệ giữa entry gốc và các consumer group.

### 13.1. XACKDEL: kết hợp ACK và xóa có điều kiện

Cú pháp:

```redis
XACKDEL key group [KEEPREF | DELREF | ACKED] IDS numids id [id ...]
```

Ví dụ một entry ID:

```redis
XACKDEL orders:events billing ACKED IDS 1 <ID>
```

Lệnh kết hợp việc ACK trong group được chỉ định và xử lý xóa entry theo **chính sách tham chiếu**.

Các lựa chọn quan trọng:

| Chế độ | Ý nghĩa chính |
|---|---|
| `KEEPREF` (mặc định) | ACK trong group được chỉ định rồi xóa entry khỏi Stream, **giữ** các tham chiếu PEL khác đang tồn tại |
| `DELREF` | ACK trong group được chỉ định, xóa entry và **xóa cả tham chiếu tới entry ở các group** |
| `ACKED` | ACK trong group được chỉ định và chỉ xóa entry nếu **tất cả consumer group** đã đọc và xác nhận entry ấy |

**`ACKED`** đặc biệt đáng cân nhắc khi có nhiều group: một group vừa xử lý xong sẽ không tự xóa payload trong lúc group khác chưa hoàn thành.

Tuy nhiên, ngay cả `ACKED` cũng không biến Redis thành giao dịch với database. Ứng dụng vẫn phải ACK sau khi nghiệp vụ thành công và cần idempotency nếu có retry.

### 13.2. XDELEX: xóa có chính sách thay vì XDEL đơn giản

Redis 8.2 còn có:

```redis
XDELEX key [KEEPREF | DELREF | ACKED] IDS numids id [id ...]
```

Ví dụ:

```redis
XDELEX orders:events ACKED IDS 1 <ID>
```

Với `ACKED`, Redis chỉ xóa những entry đáp ứng điều kiện đã đọc và xác nhận ở tất cả group. Đây là công cụ hữu ích cho tiến trình dọn dữ liệu có biết đến consumer groups.

Cần phân biệt:

- **`XACKDEL`**: có ngữ nghĩa ACK trong **group được chỉ định**, rồi xóa có điều kiện.
- **`XDELEX`**: tập trung xóa entry với chính sách tham chiếu, không nhận group để ACK một lượt xử lý cụ thể.
- **`XDEL`**: xóa entry truyền thống, không có cơ chế chọn chính sách như hai lệnh trên.

### 13.3. XTRIM và XADD cũng hỗ trợ chế độ mới

Redis 8.2 mở rộng các tùy chọn `KEEPREF`, `DELREF`, `ACKED` cho cơ chế trim liên quan đến `XTRIM` và `XADD`.

Ví dụ:

```redis
XTRIM orders:events ACKED MAXLEN 100000
```

Lựa chọn `ACKED` yêu cầu Redis chỉ trim những entry đã được các consumer group cần thiết xác nhận theo ngữ nghĩa của lệnh, thay vì tùy ý loại payload còn cần xử lý.

Việc áp dụng cần kiểm tra phiên bản Redis và phiên bản client/Spring Data Redis. **Không gửi lệnh 8.2 tới Redis cũ hơn**: máy chủ sẽ không hiểu cú pháp. Ở Spring Data Redis hiện đại, có thể xuất hiện API `acknowledgeAndDelete(...)`, nhưng tên và mức hỗ trợ phụ thuộc phiên bản thư viện. Với dự án dùng phiên bản cũ, có thể cần tiếp tục tách `acknowledge` và retention hoặc nâng cấp có chủ đích.

### 13.4. Khi nào không nên dùng DELREF?

`DELREF` xóa các tham chiếu trong PEL của **mọi group**, tức có thể loại bỏ dấu vết cần retry của group chưa xử lý xong. Chỉ dùng nếu chủ đích nghiệp vụ là bỏ những công việc đó và chấp nhận mất khả năng phục hồi tương ứng.

`KEEPREF` giữ tham chiếu nhưng có thể để lại dangling references khi payload đã bị xóa; `ACKED` phù hợp hơn trong nhiều tình huống cần bảo vệ các consumer group chậm.

Không nên chỉ nhìn tên “delete” mà bỏ qua tác dụng tới tiến độ xử lý.

## 14. Một số câu hỏi vận hành hay gặp

### 14.1. Đã XACK, có thể đọc lại entry bằng XRANGE không?

**Có**, nếu entry chưa bị xóa hoặc trim. `XACK` chỉ loại tham chiếu pending của group, không xóa nội dung Stream.

### 14.2. Đã XACK, group hiện tại có tự nhận lại entry khi XREADGROUP với `>` không?

Thông thường **không**. Dấu `>` lấy entry mới chưa được giao trong group; entry đã giao và ACK không trở thành “mới” lần nữa chỉ vì nó vẫn còn trong Stream.

Có thể đọc lịch sử Stream bằng `XRANGE` hoặc tạo một group mới với điểm bắt đầu phù hợp, nhưng đó là cơ chế đọc lại khác với việc retry pending của group đã ACK.

### 14.3. Đã XDEL nhưng XPENDING vẫn báo ID, có phải lỗi Redis không?

Không nhất thiết. Trong cơ chế truyền thống, tham chiếu PEL có thể tồn tại ngay cả khi payload gốc đã bị xóa. Phải phân biệt “thông điệp đang pending” với “nội dung còn sẵn để xử lý lại”.

Khi cần dọn, hãy dùng cơ chế reclaim/dọn PEL hoặc các lựa chọn xóa mới phù hợp với phiên bản Redis, thay vì mặc định XPENDING sẽ về 0 sau `XDEL`.

### 14.4. XACK trả 0 có đồng nghĩa dữ liệu đã bị xóa?

**Không.** Nó thường có nghĩa ID đó không được gỡ khỏi PEL bởi lệnh đang gọi, chẳng hạn do đã ACK trước hoặc không nằm trong pending của group được chỉ định. Dùng `XRANGE`/`XLEN` để kiểm tra dữ liệu gốc khi cần.

### 14.5. XDEL trả 1 có đồng nghĩa nghiệp vụ xử lý xong?

**Không.** Nó chỉ cho biết entry tồn tại và đã bị xóa khỏi Stream; không cho biết billing, analytics hay dịch vụ bên ngoài đã hoàn thành.

### 14.6. Có nên xóa entry ngay khi XACK thành công?

Chỉ khi **chính sách retention cho phép** và không còn consumer group hay nhu cầu đọc lại nào phụ thuộc vào payload đó. Trong hệ thống nhiều group, xóa ngay trong từng listener thường là thiết kế rủi ro.

### 14.7. Có thể đặt EXPIRE cho từng entry trong Stream không?

Redis TTL thông thường áp dụng cho **key Stream**, không phải từng entry độc lập. `EXPIRE orders:events 3600` có thể khiến **cả Stream key** hết hạn, không phải chỉ những entry đã xử lý.

Nếu cần giới hạn lịch sử entry, dùng `XTRIM`, chính sách `MAXLEN`/`MINID` hoặc cơ chế deletion theo phiên bản Redis và yêu cầu nghiệp vụ.

### 14.8. Nếu có consumer group tạo mới sau nhiều ngày thì sao?

Nếu group mới cần đọc lịch sử, phải bảo đảm retention chưa xóa các entry đó và chọn offset khởi đầu phù hợp. Việc một entry đã được các group hiện hữu ACK không bảo đảm lịch sử sẽ được giữ mãi cho những group tạo trong tương lai.

Do đó, chính sách retention phải có hợp đồng về thời gian có thể đọc lại và nhóm consumer được hệ thống bảo vệ.

## 15. Quan sát hệ thống bằng các lệnh Redis

Trong môi trường thử nghiệm hoặc khi điều tra sự cố, có thể dùng:

```redis
XINFO STREAM orders:events
XINFO GROUPS orders:events
XINFO CONSUMERS orders:events billing

XPENDING orders:events billing
XPENDING orders:events billing - + 20

XLEN orders:events
XRANGE orders:events - + COUNT 10
```

Ý nghĩa:

| Lệnh | Quan sát chính |
|---|---|
| `XINFO STREAM` | Metadata Stream, số entry, thông tin đầu/cuối |
| `XINFO GROUPS` | Các group, tiến độ/phần trạng thái group |
| `XINFO CONSUMERS` | Consumers trong một group và lượng pending |
| `XPENDING` | Pending chưa ACK của group |
| `XLEN` | Số entry còn được giữ trong Stream |
| `XRANGE` | Dữ liệu entry còn trong Stream |

Không nên liên tục chạy `XRANGE stream - +` trên Stream rất lớn trong luồng request chỉ để kiểm tra trạng thái. Dùng `COUNT`, phân trang, thống kê Stream và metric ứng dụng phù hợp.

Các metric nên theo dõi:

- **Pending count** theo group.
- Tuổi/idle time của pending cũ nhất.
- Tốc độ nhận, xử lý thành công và ACK.
- Số lần reclaim/retry và số event vượt giới hạn retry.
- Số entry/byte của Stream, tốc độ tăng trưởng.
- Số entry bị trim/xóa và tỷ lệ payload thiếu.
- Trạng thái consumer group chậm nhất.
- Lỗi nghiệp vụ, timeout và số lần xử lý idempotent do message lặp.

Tổng `XLEN` nhỏ nhưng pending count lớn có thể báo hiệu payload đã bị trim/xóa quá sớm hoặc có vấn đề vòng đời. Tổng `XLEN` tăng liên tục nhưng pending = 0 ở mọi group có thể cho thấy chính sách retention chưa được áp dụng.

## 16. Thiết kế quy trình xử lý an toàn

Một quy trình thực tế có thể chia trách nhiệm thành ba thành phần:

```text
            Producer
               |
               | XADD
               v
             STREAM
               |
        +------+-------+
        |              |
        v              v
    Group billing    Group analytics
        |              |
    xử lý + ACK     xử lý + ACK
        |              |
        +------+-------+
               |
         Retention Policy
               |
   đủ điều kiện + đạt thời hạn
               |
      XTRIM / XDELEX / XDEL
```

### 16.1. Trách nhiệm của producer

- Ghi event với ID, schema và dữ liệu đủ để xử lý.
- Kiểm soát lỗi phát event, idempotency nếu producer có thể retry.
- Không đặt chính sách trim quá ngắn khiến consumer chậm bỏ lỡ.
- Nếu event bắt buộc không được mất, cân nhắc outbox và cơ chế persist/replication phù hợp.

### 16.2. Trách nhiệm của consumer

- Đọc qua group và lưu trạng thái pending.
- Xử lý có idempotency.
- **ACK chỉ sau khi hoàn thành phần nghiệp vụ cần thiết**.
- Để pending khi gặp lỗi cần retry.
- Có cơ chế reclaim pending bị bỏ lại khi worker chết.
- Không tự `XDEL` chỉ vì vừa ACK thành công.

### 16.3. Trách nhiệm của retention

- Biết hệ thống có bao nhiêu group quan trọng.
- Định nghĩa thời hạn giữ lịch sử và điều kiện xóa.
- Theo dõi các group chậm, pending bị bỏ quên.
- Đánh giá nguy cơ xóa payload trước khi group khác xử lý.
- Với Redis 8.2+, cân nhắc các chế độ `ACKED` để tránh xóa sớm.
- Thử trên môi trường phát triển trước khi thay đổi cách trim/xóa.

### 16.4. Thế nào là “an toàn” với dữ liệu quan trọng?

Redis Streams có dữ liệu lưu trong Redis và metadata consumer group, nhưng khả năng giữ dữ liệu còn phụ thuộc vào cấu hình persistence, replication, failover và retention của cụm. Không nên gọi “đã XACK” là bằng chứng đủ cho mọi cam kết bền vững xuyên nhiều hệ thống.

Đối với thanh toán hoặc giao dịch quan trọng, phải thiết kế toàn bộ đường dữ liệu: producer, nguồn dữ liệu, event, consumer, xử lý trùng lặp, retry, giám sát và chính sách lưu giữ.

## 17. Bài tập thực hành

### Bài tập A: Kiểm chứng XACK không làm giảm XLEN

1. Tạo Stream và group bằng `XGROUP CREATE ... MKSTREAM`.
2. Thêm một entry bằng `XADD`.
3. Đọc bằng `XREADGROUP ... >`.
4. Xem `XPENDING`.
5. Gọi `XACK`.
6. Xem lại `XPENDING`, `XRANGE`, `XLEN`.

Kết luận cần quan sát: PEL giảm, entry vẫn còn trong Stream.

### Bài tập B: XDEL trước ACK

1. Tạo Stream và group khác với bài A.
2. Thêm, đọc một entry để tạo pending.
3. Gọi `XDEL` khi entry còn pending.
4. Kiểm tra `XPENDING` và `XRANGE`.
5. Dùng cơ chế đọc lại/reclaim phù hợp để quan sát trường hợp ID tồn tại trong metadata nhưng payload không còn.

Kết luận: XDEL không phải thao tác ACK; việc xóa payload khi pending gây rủi ro phục hồi.

### Bài tập C: Hai group độc lập

1. Tạo `billing` và `analytics` trên cùng Stream.
2. Thêm một entry, để cả hai group nhận.
3. Chỉ gọi `XACK` trong `billing`.
4. Kiểm tra `XPENDING` của từng group.
5. Giữ entry trong Stream cho tới khi analytics xử lý xong.

Kết luận: ACK có phạm vi một group; payload của entry thuộc Stream dùng chung.

### Bài tập D: Xử lý lỗi ứng dụng

Tạo một consumer giả lập lỗi sau khi đọc. Không ACK. Kiểm tra pending, rồi khôi phục consumer hoặc reclaim bằng `XAUTOCLAIM` theo ngưỡng idle phù hợp. Xử lý lại với cơ chế chống lặp và ACK.

Kết luận: pending phục vụ retry; `XDEL` không thể thay thế cơ chế này.

### Bài tập E: Redis 8.2 và xóa có điều kiện

Nếu môi trường là Redis 8.2 trở lên, thử `XACKDEL ... ACKED` trên Stream có hai group. Xác nhận entry **không bị xóa** khi group thứ hai còn chưa hoàn thành, rồi ACK ở group thứ hai và kiểm tra khả năng xóa có điều kiện.

Không chạy ví dụ này trên phiên bản Redis cũ hơn và không dùng chung với dữ liệu nghiệp vụ thật.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Consumer đã gọi `XACK`. Vì sao `XRANGE` vẫn nhìn thấy entry?

Vì `XACK` chỉ xác nhận trong consumer group bằng cách gỡ tham chiếu PEL; nó không xóa nội dung bản ghi trong Stream.

**Câu 2.** `XDEL` có làm pending của mọi group biến mất không?

Không phải theo cơ chế `XDEL` truyền thống. Lệnh xóa entry gốc; PEL có thể còn tham chiếu tới ID đã bị xóa. Redis 8.2 cung cấp những lựa chọn xóa nâng cao để kiểm soát các tham chiếu đó.

**Câu 3.** Một group `billing` đã ACK nhưng `analytics` chưa xử lý. Có nên XDEL ngay không?

Thông thường không, vì analytics có thể còn cần payload. Hãy tách ACK theo group khỏi chính sách retention toàn Stream.

**Câu 4.** Tại sao ACK phải sau khi database commit?

Nếu ACK trước rồi nghiệp vụ lỗi, entry có thể không còn pending để retry. Nếu commit xong nhưng crash trước ACK, có thể xử lý lại bằng idempotency rồi ACK.

**Câu 5.** Pending = 0 có nghĩa Stream trống không?

Không. Pending chỉ cho biết số entry chưa ACK trong một consumer group, không phải số entry lưu trong Stream. Dùng `XLEN` để xem số entry còn giữ.

**Câu 6.** `XREADGROUP ... >` có tự lấy lại pending cũ của consumer đã chết không?

Không. `>` lấy entry mới chưa được giao cho group. Dùng cách đọc pending history hoặc claim/reclaim như `XAUTOCLAIM` tùy nhu cầu phục hồi.

**Câu 7.** Nếu một entry bị trim nhưng đang pending, điều gì có thể xảy ra?

Payload bị loại khỏi Stream trong khi PEL còn ID, khiến việc retry không lấy được nội dung. Chính sách retention phải tính tới các group và pending.

**Câu 8.** `XACKDEL ... ACKED` từ Redis 8.2 hỗ trợ điều gì?

Nó kết hợp ACK cho group được chỉ định với xóa có điều kiện khi entry đã được các group liên quan đọc và xác nhận, giúp tránh xóa sớm trước khi các group khác hoàn thành.

**Câu 9.** Vì sao ACK thành công không chứng minh mọi tác dụng phụ chỉ diễn ra một lần?

Vì consumer có thể đã xử lý thành công trước đó rồi crash trước ACK, khiến message được phát lại. Cần thiết kế idempotency ở tầng nghiệp vụ.

**Câu 10.** Khi cần bỏ một thông điệp lỗi vĩnh viễn thì nên làm gì?

Cần chính sách xử lý lỗi rõ ràng, ví dụ ghi sang dead-letter stream/queue theo yêu cầu, lưu lý do lỗi và chỉ ACK khi việc chuyển giao/xử lý lỗi đã hoàn thành. Không mặc định XDEL để che giấu các lỗi xử lý.

## 19. Ghi nhớ

- **`XACK` xác nhận xử lý trong một consumer group**, gỡ ID khỏi PEL của group đó nhưng **không xóa payload** của entry trong Redis Stream.
- **`XDEL` xóa entry gốc khỏi Stream**, không phải ACK; những tham chiếu PEL đang chờ có thể vẫn còn và mất payload để retry.
- **`XPENDING` và `XLEN` đo hai thứ khác nhau**: công việc chưa xác nhận của một group so với số entry còn được lưu.
- **ACK sau nghiệp vụ thành công**; xử lý lỗi bằng pending/reclaim và idempotency thay vì xóa dữ liệu sớm.
- **Nhiều consumer group là các tiến độ độc lập**. Một group đã ACK không có quyền tự quyết rằng những group khác không cần entry.
- **Retention là chính sách riêng**. Dùng `XTRIM`, xóa có điều kiện và quan sát group chậm; Redis 8.2+ có `XACKDEL`, `XDELEX` và các chế độ `KEEPREF`, `DELREF`, `ACKED`.
- Không đồng nhất “ACK thành công” với “giao dịch nghiệp vụ đúng một lần” hoặc “dữ liệu đã được giải phóng khỏi Stream”.

### Tài liệu tham khảo

- [Redis — XACK](https://redis.io/docs/latest/commands/xack/).
- [Redis — XDEL](https://redis.io/docs/latest/commands/xdel/).
- [Redis — XPENDING](https://redis.io/docs/latest/commands/xpending/).
- [Redis — XREADGROUP](https://redis.io/docs/latest/commands/xreadgroup/).
- [Redis — XAUTOCLAIM](https://redis.io/docs/latest/commands/xautoclaim/).
- [Redis — XACKDEL (Redis 8.2+)](https://redis.io/docs/latest/commands/xackdel/).
- [Redis — XDELEX (Redis 8.2+)](https://redis.io/docs/latest/commands/xdelex/).
- [Redis — XTRIM](https://redis.io/docs/latest/commands/xtrim/).
- [Redis — Streams](https://redis.io/docs/latest/develop/data-types/streams/).
- [Spring Data Redis — Redis Streams](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html).
- [Spring Data Redis — StreamOperations API](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/core/StreamOperations.html).
