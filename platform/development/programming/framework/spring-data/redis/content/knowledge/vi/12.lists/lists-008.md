# Lựa chọn List hay Streams theo yêu cầu xử lý công việc

Khi xây dựng hệ thống xử lý công việc bất đồng bộ bằng **Spring Data Redis**, ta thường cần một **hàng đợi**: API hoặc producer tạo công việc, còn một hoặc nhiều worker nhận và xử lý sau. Redis cung cấp ít nhất hai cấu trúc dữ liệu thường được cân nhắc cho mục đích này:

- **Redis List:** danh sách có thứ tự, phù hợp để tạo hàng đợi đơn giản bằng các lệnh `LPUSH`, `RPOP`, `BLPOP`, `BRPOP` hoặc `BLMOVE`.
- **Redis Streams:** luồng bản ghi có ID, hỗ trợ đọc theo vị trí, **consumer groups**, **pending entries** và **acknowledgement (ACK)** bằng các lệnh như `XADD`, `XREADGROUP`, `XACK`, `XPENDING` và `XAUTOCLAIM`.

Hai cấu trúc đều có thể chuyển một công việc từ producer đến consumer, nhưng **khác nhau ở việc công việc được giữ lại ra sao, có xác nhận xử lý hay không, phục hồi khi worker lỗi như thế nào và nhiều consumer phối hợp ra sao**.

> Ý chính: **List** phù hợp với hàng đợi đơn giản khi chấp nhận hoặc tự thiết kế cơ chế phục hồi. **Streams + consumer group** phù hợp hơn khi cần theo dõi công việc đã giao nhưng chưa được xác nhận, retry và quan sát backlog. Tuy nhiên, Streams không tự đem lại bảo đảm *exactly-once* hay thay thế việc thiết kế idempotency.

## 1. Bắt đầu từ yêu cầu của một công việc, không bắt đầu từ tên lệnh

Giả sử hệ thống đặt hàng có một API nhận yêu cầu xuất hóa đơn. Việc xử lý có thể mất vài giây, nên API đẩy job vào Redis và trả phản hồi, còn worker thực hiện sau:

~~~text
      POST /orders/42/invoice
                  |
                  v
           Invoice API
                  |
             enqueue job
                  v
              Redis
                  |
                  v
            Invoice Worker
                  |
        tạo hóa đơn, gửi email...
                  |
                  v
             hoàn thành
~~~

Trước khi chọn List hoặc Streams, phải trả lời:

1. Nếu worker **nhận job rồi crash** trước khi xử lý, job có được thử lại không?
2. Nếu một job được xử lý **hai lần**, nghiệp vụ có an toàn không?
3. Nhiều worker cần **chia nhau** công việc hay nhiều hệ thống phải **cùng nhận** từng sự kiện?
4. Có cần xem job nào **đang chờ**, **đã giao** nhưng chưa xác nhận, hoặc **thất bại nhiều lần** không?
5. Job phải được giữ lại bao lâu? Có giới hạn dữ liệu và chính sách dọn dẹp không?
6. Có cần lưu dấu vết sự kiện để consumer đến sau đọc lại không?
7. Công việc có phụ thuộc nghiêm ngặt vào thứ tự xử lý không?
8. Redis chỉ là **queue hỗ trợ** hay là một thành phần quan trọng cần khả năng phục hồi, quan sát và điều phối rõ ràng?

Hai giải pháp tạo ra câu trả lời khác nhau, dù đều chạy trên cùng Redis Server và đều có thể dùng thông qua Spring Data Redis.

## 2. Bảng so sánh nhanh: Redis List và Redis Streams

| Tiêu chí | Redis List | Redis Streams |
|---|---|---|
| Cấu trúc | Dãy phần tử có thứ tự | Dãy bản ghi có **ID** và các field |
| Ghi job | `LPUSH` / `RPUSH` | `XADD` |
| Đọc job | `LPOP` / `RPOP` hoặc lệnh blocking | `XREAD` hoặc `XREADGROUP` |
| Khi consumer lấy job theo cách đơn giản | Pop **loại phần tử khỏi List** | Read **không tự xóa bản ghi khỏi Stream** |
| Chờ có dữ liệu | `BLPOP` / `BRPOP` / `BLMOVE` | `XREAD BLOCK` / `XREADGROUP BLOCK` |
| Consumer group tích hợp | Không | Có, thông qua `XGROUP` và `XREADGROUP` |
| Theo dõi giao nhưng chưa ACK | Không có sẵn nếu chỉ pop trực tiếp | Có **Pending Entries List (PEL)** cho consumer group |
| ACK công việc đã xử lý | Không có lệnh ACK native cho một pop đơn giản | `XACK` |
| Thu hồi công việc từ consumer lỗi | Phải tự thiết kế, ví dụ processing List + timeout | `XCLAIM` / `XAUTOCLAIM`, kèm chính sách retry |
| Nhiều consumer cùng chia tải | Các pop cạnh tranh cùng List | Consumer trong cùng group chia nhau bản ghi mới |
| Nhiều nhóm nhận cùng một sự kiện | Phải tự nhân bản dữ liệu/cơ chế riêng | Mỗi consumer group có vị trí và trạng thái xử lý riêng |
| Đọc lại dữ liệu cũ | Không khi đã pop khỏi List | Có thể khi bản ghi còn được giữ; cần sử dụng offset/group thích hợp |
| Độ phức tạp ứng dụng | Thấp với queue tối giản | Cao hơn: group, ID, ACK, pending, retry, retention |
| Chi phí metadata | Cấu trúc queue đơn giản | Thêm ID, group và trạng thái pending/consumer |
| Trường hợp phù hợp | Công việc ngắn, đơn giản, chấp nhận mất job hoặc có phục hồi tự xây | Job cần ACK, retry, theo dõi pending, nhiều consumer/group |

**List không phải “không dùng được cho queue tin cậy”**: ta có thể xây thêm processing list và cơ chế xác nhận. Nhưng Redis **Streams cung cấp nhiều thành phần quản lý đó sẵn ở mức giao thức**, nên khi yêu cầu phục hồi phức tạp, việc tự xây trên List dễ trở nên tốn công và khó vận hành.

## 3. Redis List: hiểu hàng đợi đơn giản

Redis List lưu các phần tử theo thứ tự từ **trái (head)** sang **phải (tail)**. Các lệnh:

~~~text
LPUSH key value   -> thêm vào bên trái
RPUSH key value   -> thêm vào bên phải
LPOP  key         -> lấy và xóa bên trái
RPOP  key         -> lấy và xóa bên phải
BLPOP key timeout -> chờ phần tử bên trái nếu List rỗng
BRPOP key timeout -> chờ phần tử bên phải nếu List rỗng
~~~

Để tạo hàng đợi **FIFO (first in, first out)**, có thể phối hợp:

- **LPUSH + RPOP/BRPOP**: producer thêm bên trái, consumer lấy bên phải.
- Hoặc **RPUSH + LPOP/BLPOP**: producer thêm bên phải, consumer lấy bên trái.

### 3.1. Minh họa LPUSH + BRPOP

Giả sử ban đầu List rỗng:

~~~text
LPUSH jobs:ready job-1
LPUSH jobs:ready job-2
LPUSH jobs:ready job-3

Trái (head)                  Phải (tail)
  [job-3]  [job-2]  [job-1]

BRPOP jobs:ready 5  -> nhận job-1

List còn lại:
  [job-3]  [job-2]
~~~

Job được pop ra khỏi List, nghĩa là **Redis không còn giữ phần tử đó trong List nguồn**. Đây vừa là ưu điểm của một queue đơn giản (không phải ACK để xóa bản ghi khỏi nguồn), vừa là rủi ro khi worker crash.

### 3.2. Thử bằng redis-cli

Trên Redis dùng cho bài lab:

~~~bash
DEL demo:jobs:ready
LPUSH demo:jobs:ready job-1
LPUSH demo:jobs:ready job-2
LRANGE demo:jobs:ready 0 -1
BRPOP demo:jobs:ready 5
BRPOP demo:jobs:ready 5
BRPOP demo:jobs:ready 5
~~~

Hai lời gọi BRPOP đầu nhận hai job. Lần thứ ba chờ tối đa năm giây khi List rỗng rồi trả kết quả rỗng.

**Timeout của BRPOP** là thời gian chờ item, không phải thời gian “Redis giữ job sau khi worker nhận”. Đối với API đồng bộ, lời gọi blocking có thể giữ một worker thread phía Java và một connection đang thực hiện lệnh. Nên chạy consumer trong background worker có giới hạn, không chờ BRPOP trực tiếp trong đường request HTTP nếu không có lý do rõ ràng.

## 4. Rủi ro quan trọng của List: pop trước, xử lý sau

Xét consumer viết theo cách trực tiếp:

~~~text
T0: Redis List có job-42
T1: Worker A gọi BRPOP -> Redis loại job-42 khỏi List
T2: Worker A gọi API tạo hóa đơn
T3: Worker A crash trước khi lưu hóa đơn
~~~

Tại **T3**, job không còn trong List nguồn. Nếu không có hệ thống khác lưu trạng thái job hoặc cơ chế requeue, không còn bản ghi để consumer khác lấy lại.

~~~text
 Redis List       Worker A            Database
     |               |                   |
     | -- job-42 ---> |                   |
     | (pop mất job)  |                   |
     |               X crash             |
     |               |                   |
     |        không có ACK/retry native   |
~~~

Đây là ranh giới của kiểu **destructive pop**. Cách này hợp lý cho công việc:

- Có thể tạo lại từ nguồn dữ liệu khác.
- Không quá nghiêm trọng nếu mất một job đơn lẻ.
- Có cơ chế đối chiếu/sửa lỗi ngoài Redis.
- Có thời gian xử lý ngắn và vận hành đơn giản.

Nhưng sẽ không phù hợp nếu xử lý thất bại đồng nghĩa **đánh mất một nghiệp vụ bắt buộc** mà hệ thống không thể phục hồi.

### 4.1. Nhiều consumer cùng pop có xử lý trùng không?

Nếu hai consumer gọi `BRPOP` trên cùng List, một phần tử bị pop **chỉ giao cho một lời gọi pop thành công** ở phía Redis tại thời điểm đó. Điều này giúp chia tải trong mô hình nhiều worker.

Tuy nhiên:

- Redis không đảm bảo worker xử lý xong sau khi đã pop.
- Nếu producer đẩy **hai bản ghi cùng jobId**, hai consumer có thể xử lý cùng một nghiệp vụ hai lần.
- Nếu có logic retry bên ngoài, job có thể được đưa lại hàng đợi và chạy lại.

Vì vậy, ngay cả mô hình List cũng cần **idempotency** cho tác vụ nhạy cảm.

## 5. Muốn dùng List đáng tin cậy hơn: ready list và processing list

Để không mất job ngay sau khi dequeue, có thể dùng **hai List**:

~~~text
jobs:ready                  jobs:processing
    |                              ^
    |                              |
    +-- BLMOVE RIGHT LEFT ---------+
              (atomic move)
                        |
                      Worker
                        |
             xử lý thành công?
                 /           \
               Có            Không/crash
               |                |
      LREM khỏi processing    Job còn trong
                            processing list
~~~

Redis có lệnh `LMOVE`/`BLMOVE` để **di chuyển atomically một phần tử từ List nguồn sang List đích**. `BLMOVE` có thể chờ nếu List nguồn rỗng.

Ví dụ:

~~~bash
LPUSH jobs:ready job-42
BLMOVE jobs:ready jobs:processing RIGHT LEFT 5
~~~

Sau lệnh, job được gỡ khỏi `jobs:ready` nhưng được giữ trong `jobs:processing` trước khi worker xử lý. Khi xử lý thành công:

~~~bash
LREM jobs:processing 1 job-42
~~~

Ở đây, `LREM` đóng vai trò tương đương **xác nhận hoàn thành do ứng dụng tự thiết kế**. Nó không phải ACK native có trạng thái consumer như Redis Streams.

### 5.1. Vì sao cách này vẫn phải tự xây nhiều thứ?

Processing List chỉ giúp lưu lại phần tử sau khi chuyển:

1. **Ai đang sở hữu job?** Nếu nhiều worker dùng chung processing list, cần biết job thuộc worker nào.
2. **Job bị kẹt bao lâu?** Cần lưu thời điểm giao hoặc lease deadline, không chỉ lưu payload.
3. **Khi nào retry?** Một process quét processing list hoặc index phải xác định job quá hạn.
4. **Làm sao tránh retry cùng lúc với worker cũ vẫn đang xử lý?** Cần trạng thái ownership, lease/fencing hoặc idempotency.
5. **Làm sao tránh `LREM` xóa nhầm phần tử?** Nên dùng job ID duy nhất hoặc envelope định danh độc nhất.
6. **Thứ tự có bị thay đổi khi requeue?** Có thể, và cần được chấp nhận hoặc xử lý.
7. **Xóa job đã hoàn tất nhưng crash trước bước xác nhận thì sao?** Job được retry và có thể được xử lý hai lần.

Redis Streams cung cấp một phần lớn khả năng này qua **consumer group, delivery count, PEL, ACK và claim**, nên là lựa chọn đáng cân nhắc khi hệ thống bắt đầu cần những yêu cầu trên.

**Không nên dùng BRPOPLPUSH cho thiết kế mới chỉ vì ví dụ cũ:** trên Redis hiện đại, `LMOVE`/`BLMOVE` là các lệnh nên tìm hiểu trước. Việc tương thích phiên bản Redis Server và driver vẫn cần được xác định.

## 6. Redis Streams: bản ghi có ID thay vì phần tử bị pop ngay

Redis Streams là cấu trúc dạng **append-only log có thứ tự theo ID**. Producer thêm một bản ghi bằng `XADD`. Mỗi bản ghi có:

- **Stream key:** tên của luồng, ví dụ `jobs:invoice:stream`.
- **Record ID:** định danh bản ghi, thường hiển thị dưới dạng `milliseconds-sequence`.
- **Fields và values:** dữ liệu công việc, ví dụ `jobId`, `type`, `orderId`.

Ví dụ:

~~~bash
XADD jobs:invoice:stream * jobId job-42 type CREATE_INVOICE orderId 42
XADD jobs:invoice:stream * jobId job-43 type CREATE_INVOICE orderId 43
~~~

Redis trả các ID tương tự:

~~~text
"1762965000000-0"
"1762965000001-0"
~~~

Đây chỉ là **ID minh họa**, không phải ID cần hardcode. Khi truyền `*`, Redis tự sinh ID phù hợp với quy tắc của Streams.

Khác với Redis List pop:

~~~text
List:
  BRPOP -> phần tử rời khỏi List nguồn

Streams:
  XREAD / XREADGROUP -> bản ghi được đọc/giao
                        nhưng vẫn có thể còn trong Stream
  XACK -> xác nhận một nhóm đã xử lý,
          KHÔNG tự xóa bản ghi khỏi Stream
~~~

Khả năng giữ lại record ID và dữ liệu giúp Streams phù hợp với nhiều yêu cầu quản lý job hơn.

### 6.1. Stream không phải queue “lưu mãi”

Dữ liệu còn tồn tại cho tới khi bị xóa/trimming hoặc key bị xóa/eviction tùy cấu hình. Ngoài ra, độ bền qua restart/failover phụ thuộc cấu hình **Redis persistence (RDB/AOF)**, replication và vận hành.

Streams **không tự đảm bảo không mất dữ liệu trong mọi sự cố**. Khi yêu cầu độ bền rất cao, cần thiết kế và đánh giá toàn bộ đường ghi, persistence, retention, failover, producer retry và storage nghiệp vụ.

## 7. Hai kiểu đọc Streams: XREAD và XREADGROUP

### 7.1. XREAD: đọc theo vị trí, không bắt buộc có group

Ví dụ:

~~~bash
XREAD COUNT 10 STREAMS jobs:invoice:stream 0-0
~~~

Client đọc các bản ghi có ID lớn hơn offset đã truyền. Nếu đọc xong muốn tiếp tục từ đâu, **client phải ghi nhớ ID cuối cùng** khi dùng kiểu đọc này. Nếu mất offset và chọn vị trí mới không phù hợp, ứng dụng có thể bỏ qua hoặc đọc lại dữ liệu.

Với `XREAD BLOCK`, client có thể chờ record mới khi chưa có dữ liệu thích hợp.

**XREAD không tự tạo consumer group hay PEL**. Nếu có ba consumer độc lập cùng đọc stream từ cùng offset, cả ba đều có thể nhận cùng các record. Vì vậy, không dùng XREAD với giả định Redis sẽ tự chia mỗi job cho đúng một consumer.

### 7.2. XREADGROUP: phân phối công việc trong một consumer group

Consumer group có:

- Tên group.
- Vị trí giao các bản ghi mới (last-delivered ID).
- Các consumer thuộc group.
- **Pending Entries List (PEL)** ghi nhận bản ghi đã giao nhưng chưa được ACK.

Ví dụ một group tên `invoice-workers` có hai consumer:

~~~text
                        jobs:invoice:stream
                        [ID-1][ID-2][ID-3][ID-4]
                                 |
                                 v
                   Consumer group: invoice-workers
                          /             \
                         /               \
                  consumer-a          consumer-b
                  ID-1, ID-3          ID-2, ID-4
                         \               /
                          \             /
                       Pending entries
                    cho tới khi được XACK
~~~

Sơ đồ chỉ minh họa **phân phối công việc**; không đảm bảo Redis chia đều kiểu round-robin chính xác hay tất cả consumer có tốc độ bằng nhau. Consumer nào đang sẵn sàng và gọi đọc sẽ ảnh hưởng việc giao bản ghi.

Tất cả consumer trong **cùng một group** phối hợp đọc để chia công việc. Nếu có **một group khác**, ví dụ `analytics-workers`, group đó có trạng thái đọc riêng và cũng có thể nhận các bản ghi tương ứng của cùng Stream.

## 8. Tạo consumer group và nhận công việc

Giả sử chúng ta muốn **mỗi job xuất hóa đơn được giao cho một consumer trong group**.

### 8.1. Tạo group

~~~bash
XGROUP CREATE jobs:invoice:stream invoice-workers 0 MKSTREAM
~~~

Giải thích:

- `jobs:invoice:stream`: tên Stream.
- `invoice-workers`: tên consumer group.
- `0`: group bắt đầu từ thời điểm đầu của Stream (có thể đọc backlog hiện có nếu record vẫn được giữ).
- `MKSTREAM`: tạo Stream rỗng khi chưa tồn tại.

Nếu chọn `$` làm vị trí tạo group, group sẽ bắt đầu sau các record hiện có tại thời điểm tạo, tức là chỉ xem các record mới được thêm về sau trong cách đọc thông thường. **Lựa chọn `0` hay `$` phải theo yêu cầu xử lý backlog**, không được chọn tùy tiện.

Chỉ tạo group một lần. Nếu chạy lại `XGROUP CREATE` với group đã tồn tại, Redis trả lỗi tương tự `BUSYGROUP`. Khi triển khai ứng dụng nhiều instance, cần thực hiện khởi tạo group theo cách **idempotent và kiểm soát được lỗi**, không để mọi worker tự tạo group rồi đua nhau khởi tạo mà không xử lý trạng thái đã tồn tại.

### 8.2. Ghi record

~~~bash
XADD jobs:invoice:stream * jobId job-42 orderId 42
XADD jobs:invoice:stream * jobId job-43 orderId 43
~~~

### 8.3. Consumer đọc record chưa được giao

~~~bash
XREADGROUP GROUP invoice-workers consumer-a COUNT 10 BLOCK 5000 STREAMS jobs:invoice:stream >
~~~

Các thành phần:

| Thành phần | Ý nghĩa |
|---|---|
| `GROUP invoice-workers consumer-a` | Đọc với danh tính consumer-a thuộc group |
| `COUNT 10` | Đọc tối đa một số bản ghi trong một lần gọi |
| `BLOCK 5000` | Chờ tối đa 5000 ms nếu chưa có record mới phù hợp |
| `STREAMS jobs:invoice:stream >` | Đọc các record **chưa được giao** cho consumer trong group |

Nếu có record, Redis giao cho consumer và đưa các record vào **PEL** của group, gắn với consumer tương ứng.

**Khi không có record, hết thời gian BLOCK là kết quả bình thường**, không đồng nghĩa Redis Server lỗi. Consumer có thể quay lại vòng lặp hoặc kiểm tra yêu cầu shutdown.

### 8.4. Xác nhận sau khi xử lý

Giả sử record có ID `1762965000000-0` và worker đã xử lý thành công:

~~~bash
XACK jobs:invoice:stream invoice-workers 1762965000000-0
~~~

`XACK` xóa trạng thái pending của ID đó **trong group**. Nó **không** xóa record khỏi Stream và **không** xác nhận thay cho các group khác.

Để xóa bản ghi khỏi Stream là các thao tác khác, chẳng hạn `XDEL` hoặc retention bằng `XTRIM`/`XADD ... MAXLEN`, và phải phối hợp với yêu cầu đọc lại, pending và thời hạn giữ dữ liệu.

## 9. PEL: Pending Entries List giúp biết job nào chưa được ACK

Đây là điểm khác biệt nổi bật với việc pop trực tiếp từ List.

Tại thời điểm worker nhận một record qua `XREADGROUP`, Redis lưu trạng thái **pending**:

~~~text
Stream:
  ID-1 -> job-42
  ID-2 -> job-43

Group: invoice-workers

PEL:
  ID-1 -> consumer-a (đã giao, chưa ACK)
  ID-2 -> consumer-b (đã giao, chưa ACK)
~~~

Nếu consumer-a xử lý xong và gửi:

~~~text
XACK jobs:invoice:stream invoice-workers ID-1
~~~

thì pending của ID-1 trong group được xóa. ID-2 vẫn pending cho đến khi consumer-b ACK, hoặc hệ thống thực hiện quy trình retry/claim/điều chỉnh group phù hợp.

### 9.1. Quan sát PEL bằng XPENDING

~~~bash
XPENDING jobs:invoice:stream invoice-workers
~~~

Lệnh cho thông tin tổng quan số record pending và phân bố theo consumer. Có thể xem chi tiết theo khoảng ID/count và consumer nếu cần điều tra.

Ví dụ:

~~~bash
XPENDING jobs:invoice:stream invoice-workers - + 10
~~~

Kết quả chi tiết có thể chứa **record ID**, **consumer**, **thời gian idle** và **số lần giao**. Những thông tin này giúp xác định job có vẻ bị kẹt, nhưng thời gian idle dài **chưa tự chứng minh job đã thất bại**: worker có thể đang xử lý tác vụ dài. Chính sách timeout/lease phải dựa trên thời gian xử lý thực tế.

### 9.2. XACK không phải “đánh dấu thành công trong database”

XACK chỉ sửa **trạng thái của consumer group trên Redis**. Nó không tự ghi vào cơ sở dữ liệu nghiệp vụ, không xác nhận email đã gửi thành công và không tự kết thúc một transaction liên hệ thống.

Code phải gửi ACK **sau khi công việc đã đạt mức hoàn thành theo yêu cầu**; nếu gửi ACK trước rồi xử lý thất bại, Redis có thể coi record đã được xác nhận trong khi tác vụ chưa hoàn tất.

## 10. Worker crash: tại sao phải xử lý pending?

Xét một kịch bản:

~~~text
T0  XADD job-42
T1  consumer-a XREADGROUP -> nhận job-42, đưa vào PEL
T2  consumer-a bắt đầu tạo hóa đơn
T3  consumer-a crash, chưa XACK
T4  consumer-b vẫn đang chạy
~~~

Điều quan trọng:

- Job **không tự biến mất** khỏi Stream chỉ vì được đọc.
- Group vẫn có trạng thái pending của record đã giao.
- Nhưng **consumer-b không tự nhận record đó chỉ bằng cách liên tục đọc `>`**. Dấu `>` yêu cầu record *mới, chưa được giao* cho group; job-42 đã được giao và đang pending.

Vì vậy, ngoài vòng lặp đọc record mới, một worker system dùng Streams cần **vòng phục hồi pending**.

### 10.1. Đọc lại pending của chính consumer

Một consumer có thể đọc các pending record của chính mình bằng offset phù hợp, ví dụ:

~~~bash
XREADGROUP GROUP invoice-workers consumer-a COUNT 10 STREAMS jobs:invoice:stream 0
~~~

Đây không giống `>`. Với ID khác `>`, việc đọc group liên quan tới các entry đã pending của consumer gọi lệnh theo phạm vi ID được yêu cầu. Nó giúp consumer khôi phục khi chính process đã restart và vẫn dùng cùng consumer name, nhưng **không tự thu hồi pending từ consumer khác**.

### 10.2. Thu hồi pending của consumer đã chết

Redis cung cấp `XCLAIM` và `XAUTOCLAIM`. Ví dụ:

~~~bash
XAUTOCLAIM jobs:invoice:stream invoice-workers consumer-b 30000 0-0 COUNT 10
~~~

Giải thích:

- Nhắm vào group `invoice-workers`.
- Chuyển ownership cho `consumer-b` khi entry pending đủ thời gian idle yêu cầu.
- `30000` là thời gian idle tối thiểu **30.000 milliseconds**.
- `0-0` là cursor bắt đầu quét.
- `COUNT 10` giới hạn số entry dự kiến xử lý ở lượt này.

`XAUTOCLAIM` trả về thông tin cursor và các entry được claim; logic phục hồi cần xử lý cursor qua nhiều lượt nếu backlog lớn. Cần lưu ý phiên bản Redis Server hỗ trợ lệnh này (Redis 6.2 trở lên).

**Claim không tự xử lý job hoặc tự ACK.** Consumer-b phải:

1. Kiểm tra payload, retry count và chính sách retry.
2. Xử lý lại job một cách an toàn.
3. Gửi `XACK` khi đã hoàn thành theo quy tắc.
4. Với lỗi không thể phục hồi, đưa job sang cơ chế **dead-letter** hoặc lưu trạng thái thất bại theo thiết kế nghiệp vụ.

### 10.3. Vì sao chỉ dựa vào thời gian idle là chưa đủ?

Nếu worker-a đang làm một tác vụ rất dài, một worker-b claim record chỉ vì idle quá 30 giây thì **hai worker có thể xử lý cùng job đồng thời**. Cần chọn min-idle phù hợp, có thể theo dõi thời gian xử lý/heartbeat/lease, và thiết kế idempotency hoặc fencing khi tác vụ có tác động bên ngoài.

Redis Streams hỗ trợ **phát hiện và thu hồi pending**, nhưng không tự nhận biết một tác vụ bên ngoài đã hoàn tất hay chưa.

## 11. At-most-once, at-least-once và exactly-once

Các thuật ngữ giao hàng có thể gây hiểu nhầm nếu không phân biệt **nhận message**, **xử lý nghiệp vụ** và **ghi trạng thái**.

### 11.1. List pop trực tiếp: mất job có thể xảy ra

Nếu worker pop khỏi List rồi crash, job có thể mất khỏi queue. Đây là cách làm **không có retry native sau khi pop** và có nguy cơ thất lạc công việc. Một cấu hình thường hướng đến đặc tính *at-most-once* ở bước giao qua destructive pop, nhưng duplicate vẫn có thể xuất hiện do producer, retry tầng khác hoặc payload trùng lặp.

### 11.2. Streams + xử lý rồi ACK: hướng tới at-least-once

Luồng thường dùng:

~~~text
XREADGROUP -> nhận job
    |
    v
Xử lý nghiệp vụ
    |
    v
Commit kết quả thành công
    |
    v
XACK
~~~

Nếu worker crash **trước XACK**, record còn pending và có thể được retry. Đây là nền tảng cho cơ chế **at-least-once** nếu việc giữ dữ liệu, phục hồi pending và retry được triển khai đúng.

Nhưng nếu nghiệp vụ **đã xử lý xong** mà worker crash **trước khi XACK**, job sẽ được chạy lại:

~~~text
T0: consumer-a nhận job-42
T1: tạo hóa đơn thành công ở database
T2: consumer-a crash trước XACK
T3: consumer-b claim job-42 và xử lý lại
~~~

**Chạy lại không đồng nghĩa phải tạo hai hóa đơn.** Ứng dụng cần idempotency để cùng một job ID không gây tác động nghiệp vụ hai lần.

### 11.3. Streams có đảm bảo exactly-once không?

**Không tự động.** Redis Streams không thể nguyên tử hóa việc:

- Ghi vào một database khác,
- Gọi cổng thanh toán,
- Gửi email,
- Và gửi `XACK` tới Redis,

chỉ nhờ dùng consumer group. Các thao tác ở những hệ thống khác nhau không tự tạo thành một transaction phân tán.

Một hướng thực tế:

- Gắn **jobId/idempotency key** duy nhất cho từng yêu cầu nghiệp vụ.
- Trong hệ thống lưu kết quả, ghi nhận trạng thái đã xử lý với **unique constraint** hoặc quy tắc kiểm tra atomic.
- Nếu job đã xử lý, consumer retry bỏ qua side effect và có thể ACK record.
- Với side effect bên ngoài không hỗ trợ idempotency, cần cơ chế đối soát và thiết kế riêng.

Ví dụ, job `invoice-job-42` chỉ được tạo một hóa đơn với mã nghiệp vụ có unique constraint. Khi record được retry, bước ghi vào database phát hiện hóa đơn đã có và không tạo bản thứ hai.

**Kết luận:** Streams giúp xây xử lý *at-least-once* thuận tiện hơn List pop trực tiếp, còn **exactly-once effect** là bài toán cấp hệ thống cần idempotency/transaction/outbox và ranh giới nghiệp vụ phù hợp.

## 12. Consumer groups: chia tải và nhận sự kiện ở nhiều nhóm

Với một Stream:

~~~text
              jobs:invoice:stream
                  [1][2][3][4]
                       |
             +---------+---------+
             |                   |
       Group: billing      Group: analytics
             |                   |
       +-----+-----+          +--+--+
       |           |          |     |
    worker-a    worker-b    worker-c worker-d
~~~

Hai mô hình cần phân biệt:

**Trong một group:** consumer phối hợp để chia các record mới. Mỗi record được giao cho một consumer trong group ở lần giao ban đầu; nó có thể được claim/retry nếu không ACK.

**Giữa hai group:** mỗi group có vị trí và trạng thái riêng. Cùng một record được giữ trong Stream có thể được xử lý bởi cả group billing lẫn group analytics, nếu group được khởi tạo/đọc theo cách bao gồm record đó.

Điều này hữu ích khi một sự kiện `order-created` phải kích hoạt **nhiều hệ thống độc lập**, mỗi hệ thống cần checkpoint/ACK riêng. Với Redis List đơn giản, một pop loại bỏ phần tử khỏi queue nguồn; để hai hệ thống đều nhận cùng job cần nhân bản queue hoặc tự xây cơ chế khác.

### 12.1. Tránh nhầm consumer name với group name

- **Group name** biểu thị một luồng công việc/nhóm xử lý logic, ví dụ `invoice-workers`.
- **Consumer name** biểu thị một consumer trong group, ví dụ `invoice-worker-instance-07`.

Nếu nhiều process đồng thời dùng **cùng consumer name** thiếu kiểm soát, việc theo dõi ownership/pending và khôi phục dễ trở nên rối. Thường nên dùng tên consumer ổn định theo instance/worker trong giai đoạn chạy, đồng thời có chiến lược cleanup consumer cũ và xử lý pending.

### 12.2. Thứ tự giao không bằng thứ tự hoàn thành

Streams có thứ tự ID, nhưng hai worker xử lý thời gian khác nhau:

~~~text
Record 100-0 -> worker-a, xử lý 20 giây
Record 101-0 -> worker-b, xử lý 1 giây

worker-b hoàn thành trước worker-a.
~~~

Vì vậy, **consumer group nhiều worker không bảo đảm hoàn thành theo thứ tự Stream ID**. Nếu nghiệp vụ yêu cầu per-order sequencing, phải thiết kế partition/key routing, giới hạn concurrency theo aggregate hoặc cơ chế đảm bảo thứ tự ở tầng xử lý.

## 13. Lưu dữ liệu và retention của Streams

Redis Streams **không tự xóa record khi XACK**. Điều này hữu ích nếu cần đọc lại/audit ở phạm vi nhất định, nhưng cũng khiến bộ nhớ tăng nếu không giới hạn:

~~~text
XADD mỗi giây -> Stream dài ra
XREADGROUP -> giao record
XACK -> gỡ pending trong group
       -> record vẫn nằm trong Stream
~~~

Các lệnh liên quan:

~~~bash
XLEN jobs:invoice:stream
XINFO STREAM jobs:invoice:stream
XINFO GROUPS jobs:invoice:stream
XPENDING jobs:invoice:stream invoice-workers
~~~

### 13.1. Giới hạn độ dài Stream

Ví dụ thêm record và dùng giới hạn xấp xỉ:

~~~bash
XADD jobs:invoice:stream MAXLEN ~ 100000 * jobId job-44 orderId 44
~~~

`MAXLEN ~ 100000` yêu cầu Redis cắt bớt dữ liệu theo cơ chế **approximate trimming** để kiểm soát độ dài. Kết quả không nhất thiết đúng chính xác 100.000 record; việc cắt xấp xỉ có thể hiệu quả hơn tùy workload.

Có thể chủ động thực hiện:

~~~bash
XTRIM jobs:invoice:stream MAXLEN ~ 100000
~~~

**Quan trọng:** không trim theo số lượng một cách mù quáng nếu consumer hoặc group còn cần bản ghi cũ. Tùy phiên bản Redis và lựa chọn thao tác, trimming/xóa record có thể khiến pending ID còn được tham chiếu nhưng payload đã không còn, hoặc khiến group đang chậm không đọc được dữ liệu đã bị cắt. Cần thiết kế retention dựa trên:

1. Group nào còn cần đọc các record?
2. Record nào đang pending và chưa hoàn tất?
3. Chậm nhất bao lâu một consumer có thể offline?
4. Có cần lưu DLQ/archival sang nơi bền vững khác?
5. Cần giữ lại log sau ACK bao lâu để audit hoặc replay?

Một quy trình retention đúng có thể phức tạp hơn việc đặt `MAXLEN` cố định.

### 13.2. Redis Stream cũng có thể trở thành big key

Một Stream chứa hàng chục triệu record vẫn là **một Redis key**. Trong Redis Cluster, key nằm trong một hash slot; tải đọc/ghi vào key đó tập trung vào primary node đang sở hữu slot.

Khi throughput lớn, có thể cần chia thành nhiều stream theo domain/tenant/shard hoặc thời gian, ví dụ:

~~~text
jobs:invoice:shard:0
jobs:invoice:shard:1
jobs:invoice:shard:2
jobs:invoice:shard:3
~~~

Nhưng shard làm tăng số group/consumer, routing, monitoring và có thể phá vỡ thứ tự tổng thể. Chỉ phân vùng khi có nhu cầu và số liệu đủ rõ, không tách một cách tùy tiện.

## 14. Ví dụ Spring Data Redis với Redis List

### 14.1. Cấu hình tối thiểu

Trong Spring Boot 3.x dùng Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
~~~

Ví dụ `application.yml`:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 5s
~~~

Đây là cấu hình minh họa khi Redis Server chạy trên cùng máy phát triển. Redis Server phải được triển khai riêng. Với Docker Compose, host thường là tên service Redis thay vì `localhost` bên trong container Spring Boot.

### 14.2. Producer và consumer cho queue đơn giản

~~~java
package com.example.redisjobs;

import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class SimpleListJobQueue {

    private static final String QUEUE = "jobs:invoice:list";

    private final StringRedisTemplate redis;

    public SimpleListJobQueue(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void enqueue(String jobId) {
        // LPUSH ở đầu List.
        redis.opsForList().leftPush(QUEUE, jobId);
    }

    public String receiveOnce() {
        // BRPOP ở cuối List, chờ tối đa 5 giây.
        return redis.opsForList().rightPop(
                QUEUE,
                Duration.ofSeconds(5)
        );
    }
}
~~~

Ý nghĩa:

- `enqueue("job-42")` đưa ID vào queue.
- `receiveOnce()` chờ tối đa năm giây; trả job ID nếu có.
- Nếu queue rỗng hết thời gian chờ, kết quả thường là `null`.
- Khi trả job ID, phần tử đã bị **pop khỏi List**, không có bước ACK native.

**Hãy chạy `receiveOnce()` ở background worker**, không gọi trong event-loop reactive hoặc request HTTP mà không kiểm soát thời gian chờ. Mỗi lời gọi blocking giữ thread phía ứng dụng đang chờ và có thể dùng connection chuyên biệt tùy driver/factory.

### 14.3. Consumer xử lý một lần

~~~java
public void processOneListJob(
        SimpleListJobQueue queue,
        InvoiceProcessor processor) {

    String jobId = queue.receiveOnce();
    if (jobId == null) {
        // Không có job trong 5 giây; đây không phải lỗi.
        return;
    }

    processor.process(jobId);
}
~~~

`InvoiceProcessor` ở đây là abstraction của nghiệp vụ, ví dụ component có method `void process(String jobId)`. Ví dụ **không tự bổ sung retry**. Nếu `processor.process(jobId)` ném exception sau khi pop, ứng dụng phải có chính sách xử lý riêng; Redis List không tự đặt job về hàng đợi.

## 15. Ví dụ Spring Data Redis với Streams

Streams yêu cầu thêm một vài khái niệm: record, group, consumer identity, offset và ACK.

### 15.1. Khởi tạo group trong môi trường thử nghiệm

Để mã Java phía dưới tập trung vào producer/consumer, trước tiên tạo group bằng redis-cli:

~~~bash
XGROUP CREATE jobs:invoice:stream invoice-workers 0 MKSTREAM
~~~

Lệnh này chỉ cần chạy một lần cho group. Trong ứng dụng production, việc khởi tạo group nên được tổ chức thành một bước provisioning/migration idempotent và có xử lý tình huống group đã tồn tại.

### 15.2. Producer thêm record bằng StreamOperations

~~~java
package com.example.redisjobs;

import java.util.Map;

import org.springframework.data.redis.connection.stream.RecordId;
import org.springframework.data.redis.connection.stream.StreamRecords;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class InvoiceStreamProducer {

    private static final String STREAM = "jobs:invoice:stream";

    private final StringRedisTemplate redis;

    public InvoiceStreamProducer(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public RecordId enqueue(String jobId, String orderId) {
        return redis.opsForStream().add(
                StreamRecords.string(Map.of(
                        "jobId", jobId,
                        "orderId", orderId,
                        "type", "CREATE_INVOICE"
                )).withStreamKey(STREAM)
        );
    }
}
~~~

API `StreamRecords.string(...).withStreamKey(...)` tạo một record với field/value dạng chuỗi và xác định Stream đích. `opsForStream().add(...)` gửi thao tác tương đương `XADD` và trả `RecordId` khi ghi thành công trong ngữ cảnh gọi đồng bộ thông thường.

**RecordId của Stream và jobId nghiệp vụ là hai định danh khác nhau:**

- `RecordId` (ví dụ `1762965000000-0`) định danh bản ghi trên Redis Stream, dùng cho ACK/pending.
- `jobId` (ví dụ `invoice-job-42`) định danh công việc nghiệp vụ, dùng cho idempotency và đối soát.

Nếu producer retry sau khi request tới Redis bị timeout nhưng lệnh XADD đã thực sự hoàn tất, **cùng jobId có thể xuất hiện trong hai record ID khác nhau**. Nên sử dụng idempotency key ở cấp nghiệp vụ thay vì tin rằng RecordId tự khử trùng lặp.

### 15.3. Consumer đọc record mới và ACK sau khi xử lý

~~~java
package com.example.redisjobs;

import java.time.Duration;
import java.util.List;
import java.util.Map;

import org.springframework.data.redis.connection.stream.Consumer;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.connection.stream.StreamReadOptions;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class InvoiceStreamConsumer {

    private static final String STREAM = "jobs:invoice:stream";
    private static final String GROUP = "invoice-workers";

    private final StringRedisTemplate redis;
    private final InvoiceProcessor processor;

    public InvoiceStreamConsumer(
            StringRedisTemplate redis,
            InvoiceProcessor processor) {
        this.redis = redis;
        this.processor = processor;
    }

    public void pollOnce(String consumerName) {
        List<MapRecord<String, Object, Object>> records =
                redis.opsForStream().read(
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
            // Không có record mới trong thời gian chờ.
            return;
        }

        for (MapRecord<String, Object, Object> record : records) {
            Map<Object, Object> fields = record.getValue();
            String jobId = String.valueOf(fields.get("jobId"));

            // Cần xử lý nghiệp vụ idempotent, có kiểm tra payload.
            processor.process(jobId);

            // ACK chỉ sau khi process(...) hoàn tất theo tiêu chí nghiệp vụ.
            redis.opsForStream().acknowledge(
                    STREAM, GROUP, record.getId());
        }
    }
}
~~~

Ở ví dụ này, một background worker gọi `pollOnce("invoice-worker-1")` nhiều lần theo vòng đời được ứng dụng quản lý. Mỗi lời gọi đọc tối đa 10 record mới và block tối đa hai giây nếu chưa có dữ liệu.

Các bước:

1. `Consumer.from(GROUP, consumerName)` cung cấp danh tính group/consumer.
2. `ReadOffset.lastConsumed()` trong ngữ cảnh group dùng để đọc các record mới chưa giao tương ứng với `>`.
3. `StreamReadOptions` xác định `COUNT` và `BLOCK`.
4. `processor.process(jobId)` xử lý nghiệp vụ.
5. `acknowledge(...)` gửi `XACK` cho record đã xử lý thành công.

**Nếu `processor.process(...)` ném exception, record không được ACK ở đoạn code này** và ở lại pending. Tuy nhiên, đó mới là bước đầu: ví dụ **chưa triển khai cơ chế thu hồi pending, retry, DLQ, giới hạn số lần thử, hoặc xử lý shutdown**, là những phần cần có theo yêu cầu vận hành thực tế.

### 15.4. Tại sao không ACK trong finally?

Đây là anti-pattern:

~~~java
try {
    processor.process(jobId);
} finally {
    redis.opsForStream().acknowledge(
            STREAM, GROUP, record.getId());
}
~~~

Nếu xử lý thất bại, `finally` vẫn ACK khiến record bị xóa khỏi PEL, giảm khả năng retry. **Chỉ ACK khi đã quyết định job thật sự hoàn thành hoặc đã được chuyển sang cơ chế xử lý lỗi có chủ đích.**

### 15.5. Error handling trong ví dụ cần bổ sung gì?

Code đơn giản cần được mở rộng cho sản phẩm thật:

- **Kiểm tra payload:** thiếu `jobId` phải được coi là record lỗi, không dùng chuỗi `"null"` làm ID.
- **Retry policy:** phân biệt lỗi tạm thời và lỗi không thể phục hồi.
- **Recovery:** định kỳ đọc/claim pending của consumer chết, không chỉ đọc `>`.
- **Idempotency:** chống side effect lặp khi job được giao lại.
- **DLQ / failure store:** ghi lại record thất bại nhiều lần và nguyên nhân điều tra.
- **Monitoring:** cảnh báo pending quá lâu, consumer không hoạt động, stream tăng bất thường.
- **Backpressure:** giới hạn số record xử lý cùng lúc theo tài nguyên nghiệp vụ.
- **Lifecycle:** không tự tạo thread vô hạn; worker cần cơ chế khởi động và dừng có kiểm soát.

## 16. StreamMessageListenerContainer: khi không muốn tự viết polling loop

Spring Data Redis cũng có các abstraction listener cho Streams, như `StreamMessageListenerContainer` và các API reactive tương ứng tùy phiên bản.

Ý tưởng:

~~~text
Spring application
      |
      v
StreamMessageListenerContainer
      |
      | poll Stream / consumer group theo cấu hình
      v
MessageListener callback
      |
      | xử lý business
      v
XACK nếu chiến lược xác nhận yêu cầu
~~~

Container giúp tổ chức polling, thread/executor và lifecycle listener. Nhưng cần phân biệt:

- **Container không tự biến mọi nghiệp vụ thành exactly-once.**
- Nếu chọn chiến lược ACK tự động, phải hiểu **thời điểm** ACK so với business processing.
- Nếu dùng manual ACK, callback phải ACK đúng group/record sau khi xử lý.
- Pending recovery, retry, poison message, retention và monitoring vẫn cần thiết kế phù hợp.

Với hệ thống chỉ có vài worker, tự dùng `StreamOperations.read(...)` trong một background worker có thể đủ để học. Khi ứng dụng tăng độ phức tạp, container có thể giảm mã điều phối nhưng **không thay thế thiết kế tính đúng đắn của xử lý job**.

## 17. Phân biệt List, Streams và Pub/Sub

Cả ba có thể xuất hiện khi trao đổi về “gửi một sự kiện qua Redis”, nhưng mục tiêu khác nhau:

| Cấu trúc/cơ chế | Dữ liệu tồn tại khi không có consumer? | Consumer offline có thể đọc bù? | Xác nhận xử lý native? |
|---|---|---|---|
| Redis List | Có, nếu phần tử vẫn còn trong List | Có thể pop sau khi online, **nếu chưa bị pop trước đó** | Không có ACK built-in cho pop đơn giản |
| Redis Streams | Có, khi record chưa bị xóa/trim | Có thể đọc lại bằng offset/group phù hợp nếu dữ liệu còn giữ | Có `XACK` theo consumer group |
| Redis Pub/Sub | Không lưu thành backlog theo cơ chế Pub/Sub cơ bản | Không replay message khi subscriber offline | Không có PEL/ACK theo message |

**Không chọn Pub/Sub làm job queue bắt buộc phải xử lý lại** chỉ vì API publish/subscribe đơn giản. Pub/Sub phù hợp với notification realtime mà mất thông điệp trong lúc subscriber offline có thể được chấp nhận hoặc có nguồn trạng thái khác để đồng bộ lại.

Streams phù hợp hơn khi muốn nhiều hệ thống theo dõi một sự kiện và cần checkpoint theo group. Nhưng **Redis Streams vẫn không phải hệ thống sự kiện bền vững vô hạn**: retention, persistence và xử lý lỗi phải được xác định rõ.

## 18. Tác động của kết nối và blocking reads

Cả `BRPOP` (List) và `XREADGROUP BLOCK` (Streams) đều có thể **chờ trên Redis connection** cho đến khi có dữ liệu hoặc hết timeout.

Trong Spring Data Redis:

- API đồng bộ như `ListOperations.rightPop(..., Duration)` sẽ giữ thread gọi trong thời gian chờ.
- `StreamOperations.read(..., StreamReadOptions.block(...))` cũng có thể chờ tương tự.
- Với Lettuce, các lệnh blocking thường sử dụng kết nối chuyên biệt theo cách cấu hình factory/driver; cần cân nhắc pool và số worker đồng thời.
- Pub/Sub dùng connection/đăng ký có vòng đời dài và không phải dạng nhận một job rồi trả ngay như pop/stream poll.

Nếu tạo 100 background worker đều block cùng lúc, cần quan sát connection pool, thread count, Redis clients, timeout và mức đồng thời. Chọn Streams không tự loại bỏ chi phí connection trong thời gian chờ.

### 18.1. Timeout của Redis và timeout client

Các thời hạn khác nhau:

| Loại timeout | Ví dụ | Ý nghĩa |
|---|---|---|
| Chờ job ở Redis List | `BRPOP queue 5` | Chờ tối đa 5 giây để có phần tử |
| Chờ record trên Stream | `XREADGROUP BLOCK 5000` | Chờ tối đa 5000 milliseconds để có record phù hợp |
| Command/client timeout | Cấu hình driver/Boot | Thời gian chờ phản hồi mà client chấp nhận |
| Pool borrow timeout | `max-wait` của pool | Thời gian chờ được cấp connection |
| Retry/visibility timeout nghiệp vụ | Chính sách ứng dụng | Khi nào job được coi là có nguy cơ kẹt và có thể claim |

Nếu `BRPOP` hết thời gian chờ và trả `null`, đó có thể là **trạng thái queue rỗng bình thường**. Nếu một worker không mượn được connection trong pool thì đó là **vấn đề tài nguyên client**. Nếu Stream có record pending quá lâu thì đó có thể là **công việc chưa ACK hoặc worker đang xử lý lâu**.

Không thể chữa cả ba trường hợp chỉ bằng cách tăng `spring.data.redis.timeout`.

## 19. Vấn đề thứ tự: FIFO chưa đủ cho job processing

List có thể giữ thứ tự pop theo FIFO nếu producer và consumer dùng đúng hai đầu của List. Streams có ID tăng theo luồng và cho phép đọc theo thứ tự logic.

Nhưng **thứ tự nhận khác với thứ tự hoàn thành**:

~~~text
Job A được giao trước -> worker-1 xử lý 15 giây
Job B được giao sau   -> worker-2 xử lý 1 giây

Job B hoàn thành trước Job A
~~~

Với yêu cầu “phải xử lý mọi sự kiện của cùng order đúng thứ tự”:

- Giới hạn concurrency theo order hoặc theo partition.
- Tránh cho nhiều worker cùng thay đổi một aggregate nếu chưa có versioning/lock.
- Dùng state machine, version field, unique constraint hoặc logic chống xử lý out-of-order.
- Khi shard theo orderId, đảm bảo cùng một order được route nhất quán, kèm giải pháp cho retry.

**Không chọn Streams chỉ vì thấy ID tăng và mặc định suy ra xử lý theo thứ tự tuyệt đối.**

## 20. Backlog, DLQ và retry: Streams giúp quản lý nhưng không tự hoàn thiện

Một hệ thống xử lý công việc thực tế thường có nhiều trạng thái:

~~~text
       NEW RECORD
           |
           v
       DELIVERED
           |
       PROCESSING
        /      \
       /        \
   SUCCESS     FAILURE
      |           |
      v           v
     XACK       retryable?
                 /    \
               Có      Không
                |        |
                v        v
           Pending /   Failure store/
           XAUTOCLAIM  Dead-letter
                |        |
                v        v
             RETRY     xử lý thủ công
~~~

### 20.1. Pending không giống failed

Một record có thể pending vì:

- Worker đang thực hiện tác vụ hợp lệ kéo dài vài phút.
- Worker crash.
- Lệnh ACK bị lỗi sau khi xử lý thành công.
- Worker gặp lỗi nhưng chưa có cơ chế xử lý.
- Worker mất kết nối giữa các bước.

Vì vậy, **pending ≠ failed**. Logic phục hồi cần thời gian chờ, thông tin delivery count, trạng thái nghiệp vụ và cơ chế hạn chế xử lý trùng.

### 20.2. Thiết kế Dead Letter Queue (DLQ)

Redis Streams không tự tạo một DLQ theo ý nghĩa “sau N lần lỗi, chuyển job tới đây”. Ứng dụng phải quy định:

1. Khi nào ngừng retry?
2. Cần lưu payload gốc, jobId, error type, last error, thời điểm nào?
3. Dữ liệu thất bại phải nằm ở một Stream/List khác hay database?
4. Ghi vào DLQ và ACK record gốc cần phối hợp ra sao?
5. Ai xử lý việc replay job từ DLQ?

Ví dụ một Stream riêng:

~~~text
jobs:invoice:stream
jobs:invoice:dlq
~~~

Khi job thất bại vĩnh viễn, worker có thể ghi bản ghi lỗi vào DLQ rồi xác nhận record gốc theo chính sách. Nếu việc ghi DLQ và ACK nằm trong nhiều lệnh độc lập, cần xem xét trường hợp crash giữa các bước; ở Redis Cluster, việc dùng script/transaction nhiều key còn chịu ràng buộc hash slot. Không được coi “có DLQ” là đảm bảo dữ liệu không bao giờ mất.

## 21. Quan sát và vận hành

### 21.1. Các chỉ số cần theo dõi với List

~~~bash
LLEN jobs:invoice:list
~~~

`LLEN` phản ánh độ dài List tại thời điểm đọc, phù hợp để quan sát backlog đang đợi pop.

Nếu dùng ready + processing:

~~~bash
LLEN jobs:ready
LLEN jobs:processing
~~~

Phải theo dõi cả processing backlog và thời gian job ở đó, không chỉ queue ready. List không tự cung cấp delivery count/consumer ownership, nên cần metadata bên ngoài nếu muốn biết ai đang giữ từng job.

### 21.2. Các chỉ số cần theo dõi với Streams

~~~bash
XLEN jobs:invoice:stream
XINFO GROUPS jobs:invoice:stream
XINFO CONSUMERS jobs:invoice:stream invoice-workers
XPENDING jobs:invoice:stream invoice-workers
~~~

Chỉ số nên có:

- Độ dài Stream và tốc độ `XADD`.
- Pending count theo group và consumer.
- Tuổi của record pending lâu nhất.
- Tốc độ xử lý thành công/ACK và retry.
- Delivery/retry count, tỷ lệ job thất bại.
- Consumer đã ngừng heartbeat/poll.
- Lag/backlog theo group khi Redis version cung cấp thông tin tương ứng.
- Memory usage, Redis CPU, command latency, network và connection pool wait.

**XLEN không tương đương số job chưa xử lý.** Đó là số entry được giữ trong Stream, gồm cả record đã ACK nhưng chưa trim. Muốn xác định backlog theo group, cần kết hợp thông tin group, pending và offset/lag, không lấy XLEN làm duy nhất một số liệu.

### 21.3. Khi nào nên xem là alarm?

Một số dấu hiệu:

- Pending tăng liên tục trong khi không có ACK.
- Một consumer không hoạt động nhưng có nhiều pending entry.
- Thời gian xử lý job tăng vượt SLA.
- Trimming bắt đầu tiến gần record cũ nhất mà consumer chậm vẫn cần.
- Bộ nhớ Redis tăng do retention không có giới hạn.
- Độ trễ mượn connection tăng khi quá nhiều consumer blocking.

Cần điều chỉnh ngưỡng theo workload, không dùng một giá trị chung cho mọi hệ thống.

## 22. Mô hình xử lý đa instance và Redis Cluster

Redis List và Stream đều là **một Redis key cho mỗi hàng đợi/luồng cụ thể**. Với Redis Cluster, mỗi key thuộc một hash slot. Vì vậy:

- Có nhiều Spring Boot instance không tự làm một Stream key phân tán trên nhiều node.
- Nhiều consumer group/consumer cùng dùng một Stream key vẫn tạo tải tập trung lên slot chứa key đó.
- Khi cần throughput cực lớn hoặc phân vùng workload, có thể chia queue/Stream thành nhiều key.
- Các lệnh cần truy cập đồng thời nhiều key trong Cluster phải xem xét **ràng buộc cùng hash slot**, ví dụ pattern ready+processing List dùng BLMOVE.

### 22.1. Lưu ý với List ready và processing trong Redis Cluster

`BLMOVE` cần thao tác **hai Redis key**. Trong Redis Cluster, các key của một lệnh đa key phải đáp ứng quy tắc cùng hash slot. Có thể dùng hash tag có chủ đích:

~~~text
jobs:{invoice}:ready
jobs:{invoice}:processing
~~~

Cả hai key có hash tag `invoice` nên thuộc cùng slot, giúp áp dụng thao tác di chuyển hai key. Nhưng mọi tải trên nhóm này cùng nằm ở một slot; nếu invoice traffic rất lớn, cần thiết kế sharding riêng.

### 22.2. Phân vùng Streams cần chú ý tính thứ tự

Ví dụ phân chia theo customerId:

~~~text
jobs:invoice:shard:0
jobs:invoice:shard:1
jobs:invoice:shard:2
~~~

Mỗi Stream có ID và group state riêng. Không có một **thứ tự toàn cục** tự động giữa các Stream. Nếu nghiệp vụ cần thứ tự theo orderId, có thể route các record của cùng order vào một shard nhất quán, nhưng vẫn phải xử lý retry/out-of-order trong cùng shard khi nhiều consumer thực hiện đồng thời.

## 23. Cách ra quyết định qua các tình huống cụ thể

### Tình huống A — Ghi log một thao tác không quan trọng, có thể mất

**Yêu cầu:** một worker hậu trường cập nhật số liệu phụ trợ; nếu mất một job nhỏ có thể tính lại từ dữ liệu gốc.

**Có thể bắt đầu với List** và `LPUSH/BRPOP`. Ưu tiên đơn giản, ít thành phần vận hành. Vẫn cần giới hạn backlog, xác định thời gian chờ và logic xử lý lỗi cơ bản.

### Tình huống B — Xuất hóa đơn bắt buộc phải xử lý

**Yêu cầu:** job không được “biến mất” sau khi worker nhận rồi crash, cần retry, theo dõi pending và tránh tạo hóa đơn trùng.

**Nên cân nhắc Streams + consumer group**, kết hợp:

- ACK sau khi ghi kết quả.
- Pending recovery bằng `XAUTOCLAIM` hoặc cơ chế tương ứng.
- Idempotency theo invoice job ID.
- Retry/backoff, DLQ/failure store.
- Retention và persistence phù hợp.

Nếu yêu cầu độ bền pháp lý/tài chính rất cao, nên xem Redis queue là **một thành phần** trong giải pháp, không phải nguồn sự thật duy nhất; cần transaction/outbox và kiến trúc lưu trữ nghiệp vụ đúng.

### Tình huống C — Gửi notification realtime cho user đang online

**Yêu cầu:** user offline sẽ lấy lại trạng thái từ API; thông báo tức thời có thể bỏ lỡ.

Có thể cân nhắc **Redis Pub/Sub** nếu đúng ngữ nghĩa realtime không replay. Không nhất thiết dùng Streams chỉ để gửi một tín hiệu không cần ACK.

### Tình huống D — Billing và analytics đều phải nhận cùng event

**Yêu cầu:** mỗi event từ order service phải được hai nhóm xử lý độc lập.

Streams với **hai consumer group** là một lựa chọn tự nhiên:

~~~text
Stream: order-events
Group 1: billing
Group 2: analytics
~~~

Mỗi group có offset, pending và ACK riêng. Một Redis List duy nhất với pop cạnh tranh sẽ chia event giữa consumer, **không** giao một bản cho mọi nhóm.

### Tình huống E — Danh sách task chờ người dùng bấm nút xử lý

**Yêu cầu:** danh sách task thuộc một user, cần hiển thị, sắp xếp hoặc xóa riêng từng task; không phải consumer group tự xử lý hậu trường.

Không nên tự động chọn Streams chỉ vì tên “task”. Có thể là **List, Sorted Set, Hash** hoặc cơ sở dữ liệu quan hệ tùy access pattern và truy vấn. Redis queue chỉ thích hợp nếu yêu cầu thực sự là **chuyển giao công việc cho consumer**.

## 24. Decision tree: chọn List hay Streams

~~~text
                Cần truyền công việc giữa producer và worker?
                               |
                  +------------+------------+
                  |                         |
                 Không                     Có
                  |                         |
            Xem kiểu dữ liệu               v
            khác phù hợp        Cần ACK/retry/pending tracking?
                                      /           \
                                    Có             Không
                                    |                |
                                    v                v
                              Redis Streams      Có chấp nhận
                              + consumer group   pop mất job không?
                                    |              /          \
                                    |            Có            Không
                                    |            |               |
                                    |            v               v
                                    |        Redis List      List + processing
                                    |        đơn giản        hoặc Streams
                                    |                            |
                                    +----------------------------+
                                                 |
                                                 v
                             Nhiều nhóm cùng cần đọc mỗi sự kiện?
                                   /                \
                                 Có                  Không
                                 |                     |
                                 v                     v
                         Streams + groups       Đánh giá độ phức tạp,
                         độc lập                tải và khả năng vận hành
                                   \                /
                                    \              /
                                     v            v
                                 Thiết kế idempotency,
                                retention, timeout, DLQ,
                                    persistence và giám sát
~~~

**Quy tắc thực tế:** ưu tiên giải pháp **đơn giản nhất đáp ứng đúng yêu cầu thất bại và phục hồi**, không phải giải pháp có ít dòng code ban đầu nhất. Một List queue ngắn có thể dễ viết nhưng rất đắt khi cần bổ sung ACK/retry về sau.

## 25. Các nhầm lẫn thường gặp

**“BRPOP giống XREADGROUP vì cả hai đều chờ job.”** Không đúng. BRPOP lấy và loại phần tử khỏi List; XREADGROUP giao record và duy trì pending cho tới khi ACK.

**“XACK xóa record khỏi Stream.”** Không. XACK xóa trạng thái pending trong một consumer group. Retention/xóa record là bước khác.

**“Consumer group tự retry mọi job lỗi.”** Không. PEL lưu pending nhưng ứng dụng phải tổ chức đọc lại/claim, xử lý lỗi và ACK theo chính sách.

**“Chỉ cần XREADGROUP với dấu > là mọi job cũ sẽ được giao lại.”** Không. Dấu > dành cho record mới chưa được giao trong group; pending phải được xử lý riêng.

**“Streams đảm bảo exactly-once.”** Không. Crash sau business commit nhưng trước ACK có thể gây xử lý lại. Cần idempotency ở cấp nghiệp vụ.

**“ACK nghĩa là dữ liệu đã bền vững trên đĩa.”** Không. ACK là xác nhận processing trong Redis group; durability qua restart/failover phụ thuộc persistence và cấu hình khác.

**“List không thể làm reliable queue.”** Không tuyệt đối. Có thể dùng ready/processing lists, atomic move và tự xây retry, nhưng độ phức tạp tăng.

**“Có hai worker trong cùng group thì mỗi worker nhận mọi event.”** Không. Cùng group là chia tải. Muốn nhiều nhóm độc lập cùng nhận, tạo các group riêng.

**“Stream record đã ACK có thể xóa ngay bất kể consumer khác.”** Không nên giả định. Group khác có thể còn cần record, hoặc chính sách audit/replay đòi retention dài hơn.

**“Thứ tự ID đảm bảo job xử lý xong đúng thứ tự.”** Không. Xử lý song song và retry có thể đổi thứ tự hoàn thành.

**“Tăng số consumer là luôn nhanh hơn.”** Không. Bị giới hạn bởi Redis node/slot, network, dependency, connection pool và bottleneck nghiệp vụ.

**“Redis Streams không bao giờ mất message.”** Không. Trim, deletion, eviction, cấu hình persistence hoặc vận hành sai đều có thể làm mất dữ liệu.

## 26. Bài thực hành có hướng dẫn

### Bài 1 — Quan sát destructive pop của List

~~~bash
DEL lab:list:jobs
LPUSH lab:list:jobs job-A job-B
LRANGE lab:list:jobs 0 -1
BRPOP lab:list:jobs 2
LRANGE lab:list:jobs 0 -1
~~~

Trả lời:

1. Phần tử nào được pop trước?
2. Nó còn xuất hiện trong `LRANGE` sau khi pop không?
3. Nếu consumer crash ngay sau BRPOP, Redis còn trạng thái nào cho biết job đang xử lý?

### Bài 2 — Quan sát processing list

~~~bash
DEL lab:list:ready lab:list:processing
LPUSH lab:list:ready job-C
BLMOVE lab:list:ready lab:list:processing RIGHT LEFT 2
LRANGE lab:list:ready 0 -1
LRANGE lab:list:processing 0 -1
LREM lab:list:processing 1 job-C
~~~

Trả lời:

1. Vì sao job vẫn còn trong Redis sau bước BLMOVE?
2. Khi worker crash trước LREM, ai sẽ tìm và retry job?
3. Nếu hai job có cùng payload `job-C`, việc LREM theo value có rủi ro gì?

### Bài 3 — Quan sát pending của Streams

~~~bash
DEL lab:stream:jobs
XGROUP CREATE lab:stream:jobs lab-workers 0 MKSTREAM
XADD lab:stream:jobs * jobId job-D
XREADGROUP GROUP lab-workers worker-1 COUNT 1 STREAMS lab:stream:jobs >
XPENDING lab:stream:jobs lab-workers
XLEN lab:stream:jobs
~~~

Sao chép **Record ID thực tế** do XADD hoặc XREADGROUP trả về. Sau đó:

~~~bash
XACK lab:stream:jobs lab-workers <record-id-thuc-te>
XPENDING lab:stream:jobs lab-workers
XLEN lab:stream:jobs
~~~

Ở đây `<record-id-thuc-te>` là placeholder, phải thay bằng ID thật (ví dụ dạng `1762965000000-0`), không gõ nguyên dấu ngoặc nhọn hay chữ placeholder.

Quan sát:

- Pending count thay đổi sau XACK.
- XLEN không tự giảm chỉ vì đã ACK.
- Consumer group quản lý trạng thái xác nhận tách khỏi dữ liệu của Stream.

### Bài 4 — Mô phỏng worker crash và claim

Trong Redis Server hỗ trợ `XAUTOCLAIM`:

1. XADD một job khác.
2. Dùng `worker-1` gọi XREADGROUP, **không ACK**.
3. Quan sát `XPENDING`.
4. Đợi quá ngưỡng idle của bài lab.
5. Dùng `worker-2` gọi `XAUTOCLAIM` để nhận pending.
6. Xử lý giả lập rồi `XACK`.

Ví dụ lệnh claim sau khi entry đủ idle:

~~~bash
XAUTOCLAIM lab:stream:jobs lab-workers worker-2 5000 0-0 COUNT 10
~~~

Trong bài lab, năm giây chỉ để dễ thử. **Không lấy 5000 ms làm ngưỡng retry production** khi job thật có thể xử lý lâu hơn.

### Bài 5 — Thiết kế idempotency

Giả sử consumer xử lý `invoice-job-42`, ghi hóa đơn vào database thành công, nhưng crash trước XACK. Khi job được claim và retry:

- Làm sao phát hiện hóa đơn đã tồn tại?
- Job ID nào là định danh nghiệp vụ bất biến?
- Unique constraint hoặc transaction database cần đặt ở đâu?
- Khi nào có thể ACK mà không tạo side effect trùng?

Viết sơ đồ trạng thái nghiệp vụ trước khi viết thêm code. Đây là phần quan trọng hơn việc nhớ chính xác một lệnh Redis.

## 27. Câu hỏi củng cố

**1. LPUSH + BRPOP phù hợp với kiểu queue nào?**

Một FIFO queue đơn giản: producer thêm bên trái, consumer lấy bên phải. Nếu List rỗng, BRPOP chờ tối đa timeout; khi pop thành công, phần tử rời List nguồn.

**2. Vì sao List pop trực tiếp có nguy cơ mất job?**

Vì phần tử đã bị xóa khỏi queue trước khi consumer xử lý xong; crash sau pop có thể để lại không có bản sao nào dùng để retry.

**3. BLMOVE giải quyết được điều gì, và chưa giải quyết được điều gì?**

BLMOVE có thể chuyển phần tử atomically từ ready sang processing List, giúp lưu lại job đang giao. Nhưng việc xác định owner, timeout, claim/requeue, ACK và retry phải được xây thêm.

**4. Redis Streams có gì khác về cấu trúc dữ liệu?**

Mỗi record có ID và field/value; đọc record không mặc nhiên xóa nó khỏi Stream. Có thể dùng offset, consumer group và cơ chế retention.

**5. PEL là gì?**

Pending Entries List, nơi consumer group theo dõi các record đã giao nhưng chưa ACK, kèm ownership và thông tin phục vụ quan sát/recovery.

**6. XACK có xóa nội dung bản ghi khỏi Stream không?**

Không. Nó xác nhận record trong một group và gỡ trạng thái pending; dữ liệu được xóa/trim theo thao tác retention riêng.

**7. Vì sao consumer mới không nhận pending cũ chỉ bằng XREADGROUP với dấu >?**

Vì dấu > dành cho record chưa được giao trong group. Pending đã có owner; cần đọc pending của chính consumer hoặc claim từ owner khác theo cơ chế phù hợp.

**8. XAUTOCLAIM có đồng nghĩa job đã được xử lý thành công không?**

Không. Nó giúp chuyển ownership của pending entry đủ idle; consumer mới vẫn phải xử lý và ACK khi hoàn tất.

**9. Có thể khẳng định Streams exactly-once không?**

Không. Một job có thể chạy lại sau crash trước ACK. Cần idempotency và ranh giới transaction đúng cho side effect nghiệp vụ.

**10. Tại sao cùng một Stream có thể được dùng cho billing và analytics?**

Mỗi consumer group có offset/pending/ACK riêng. Hai group có thể cùng xử lý một record theo mục đích khác nhau trong khi các consumer trong mỗi group chia tải với nhau.

**11. Vì sao XLEN không bằng số job chưa hoàn thành?**

Vì XLEN đếm record còn được giữ trong Stream, bao gồm record đã ACK nhưng chưa bị trim. Pending, offset/lag và trạng thái nghiệp vụ cần được quan sát riêng.

**12. Nếu consumer cần xử lý theo thứ tự tuyệt đối, cứ tăng số worker có tốt không?**

Không. Consumer chạy song song có thể hoàn thành khác thứ tự nhận. Cần thiết kế partition/serialization theo aggregate hoặc cơ chế kiểm soát thứ tự.

**13. Stream có cần giới hạn kích thước không?**

Có. Nếu không có retention, record có thể tăng liên tục và tốn bộ nhớ. Nhưng trim quá sớm có thể khiến consumer chậm hoặc pending không còn payload để xử lý.

**14. Chọn List hay Streams khi job phải retry sau worker crash?**

Streams với consumer group thường là lựa chọn tự nhiên hơn vì có PEL/ACK/claim, hoặc dùng List với ready/processing và hệ thống recovery tự xây nếu có lý do rõ ràng.

## Ghi nhớ

~~~text
REDIS LIST
  Producer: LPUSH / RPUSH
  Consumer: BRPOP / BLPOP
  -> Pop = phần tử rời List nguồn
  -> Đơn giản, nhưng crash sau pop có thể làm mất job
  -> Muốn recovery: ready/processing List + logic riêng

REDIS STREAMS
  Producer: XADD -> record ID + fields
  Consumer group: XREADGROUP
  -> Record được giao và nằm trong PEL cho tới khi ACK
  -> XACK gỡ trạng thái pending, không tự xóa Stream record
  -> XPENDING quan sát; XAUTOCLAIM/XCLAIM giúp thu hồi job kẹt
  -> Cần retry policy, idempotency, DLQ, retention, monitoring

CHỌN LIST KHI
  -> Queue nhỏ, tối giản, rủi ro sau pop được chấp nhận
     hoặc hệ thống có recovery độc lập

CHỌN STREAMS KHI
  -> Cần ACK, retry, pending tracking, consumer groups,
     đọc lại và quản lý tiến độ xử lý theo nhóm

CẢ HAI ĐỀU CẦN
  -> Kiểm soát số worker, timeout, key/slot, memory,
     kết nối, persistence và semantics nghiệp vụ
~~~

**Lựa chọn List hay Streams không nên dựa vào số dòng Java gọi Redis, mà dựa vào điều gì xảy ra khi hệ thống bị lỗi.** Nếu yêu cầu chỉ là lấy một phần tử rồi xử lý đơn giản, List có thể đủ. Nếu công việc bắt buộc được theo dõi qua các trạng thái *đã giao → đang xử lý → xác nhận*, hoặc cần phục hồi consumer lỗi và nhiều nhóm xử lý độc lập, Streams với consumer group thường là nền tảng phù hợp hơn. Dù chọn phương án nào, **idempotency, retry, retention và kiểm soát tác động nghiệp vụ** vẫn là trách nhiệm của hệ thống ứng dụng.
