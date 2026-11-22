# Giới hạn toàn broker, giới hạn address và ngưỡng dung lượng đĩa

> **Chương:** Điều tiết lưu lượng  
> **Module:** `INTEGRATION_MESSAGING_MESSAGE_BROKER_ACTIVEMQ` — vận hành Apache ActiveMQ Artemis/Classic với Java/JMS.  
> **Phạm vi trực tiếp:** Ba lớp bảo vệ tài nguyên của **Artemis**: giới hạn dùng chung toàn broker, giới hạn từng address và ngưỡng đĩa. Những cấu hình XML trong bài theo tài liệu Artemis **2.57.0**; phải đối chiếu schema/tính năng với phiên bản broker đang chạy, đặc biệt với `disk-full-policy` và `min-disk-free`.

## 1. Một broker có ba vùng áp lực khác nhau

Giả sử hai dịch vụ cùng gửi message tới Artemis:

- `lab.flow.page`: luồng giao dịch có thể tăng backlog ngắn hạn, cần **giữ message**, chấp nhận paging khi giới hạn bộ nhớ address.
- `lab.flow.fail`: luồng tác vụ không muốn chờ quá lâu, khi địa chỉ đầy phải **báo lỗi** để ứng dụng áp dụng backoff/circuit breaker.

Mỗi dịch vụ chỉ có vài MB message đang xử lý, nhưng tổng các address có thể giữ nhiều dữ liệu hơn mức broker được phép; đồng thời page files, journal và large-message files có thể dần chiếm hết volume. Cần phân biệt:

1. **Giới hạn toàn broker:** ngân sách **message memory/count** được tính trên tất cả address, ví dụ `global-max-size`, `global-max-messages`.
2. **Giới hạn riêng address:** ngưỡng message memory/count của **mỗi address**, ví dụ `max-size-bytes`, `max-size-messages` và quy tắc `address-full-policy`.
3. **Ngưỡng đĩa:** ngưỡng an toàn của **storage filesystem** mà broker giám sát, ví dụ `max-disk-usage`, `min-disk-free`; khi vượt, hành vi producer phụ thuộc `disk-full-policy`.

**Nhầm lẫn nguy hiểm:** `global-max-size=64 MiB` **không phải** giới hạn 64 MiB dung lượng file journal/paging; `max-size-bytes=2 MiB` **không** có nghĩa queue chỉ được chứa tối đa 2 MiB message khi policy là `PAGE`; `max-disk-usage=85` **không** giới hạn heap memory ở 85%.

~~~mermaid
flowchart TD
    P[JMS Producer] --> B[Artemis Broker]
    B --> G{Toàn broker: global-max-size / global-max-messages?}
    G --> A{Address: max-size-bytes / max-size-messages?}
    A -->|Chưa đạt ngưỡng| M[Giữ message theo routing bình thường]
    G -->|Chạm ngưỡng| F[Áp dụng address-full-policy của address]
    A -->|Chạm ngưỡng| F
    F -->|PAGE| PG[Paging message xuống storage]
    F -->|BLOCK| BL[Backpressure tới producer]
    F -->|FAIL| ER[Producer nhận lỗi]
    F -->|DROP| DR[Message bị bỏ]
    PG --> D{Disk usage / free-space threshold?}
    M --> D
    D -->|Dưới ngưỡng| OK[Tiếp tục ghi / lưu trữ]
    D -->|Chạm ngưỡng| DP[Áp dụng disk-full-policy]
    DP -->|BLOCK| BL
    DP -->|FAIL| ER
    DP -->|DROP| DR
~~~

Sơ đồ là mô hình ra quyết định; broker có thể kiểm tra các điều kiện trong các giai đoạn xử lý khác nhau, credit đã cấp có thể đang in-flight và một giao thức không hỗ trợ backpressure có thể nhận lỗi/ngắt kết nối. Không xem biểu đồ như mô tả tuần tự từng dòng mã nội bộ.

### Mục tiêu của bài

Sau khi học, bạn phải giải thích được *setting nằm ở đâu*, *đơn vị đo gì*, *ngưỡng tác động đến ai*, *chọn PAGE/BLOCK/FAIL/DROP ra sao*, và *kiểm chứng an toàn mà không cố làm đầy ổ đĩa thật*.

## 2. Bảng đối chiếu các ngưỡng quan trọng

| Setting | Phạm vi | Đơn vị / giá trị | Khi nào phát huy tác dụng? |
|---|---|---|---|
| `global-max-size` | **Toàn broker** | Byte message memory; cho phép ký hiệu dung lượng tùy version | Tổng memory dùng cho message trên các address đạt ngưỡng → dùng `address-full-policy` của address liên quan |
| `global-max-messages` | **Toàn broker** | Số message; `-1` là tắt | Tổng số message được theo dõi đạt ngưỡng → dùng `address-full-policy` |
| `global-max-size-percent-of-jvm-max-memory` | **Toàn broker** | % của `-Xmx` | Dùng để tính mức global memory khi chưa ấn định `global-max-size` |
| `max-size-bytes` | **Từng address** | Byte message memory; `-1` là tắt riêng ngưỡng này | Address chạm ngưỡng → `address-full-policy` |
| `max-size-messages` | **Từng address** | Số message; `-1` là tắt | Address đạt ngưỡng số message → `address-full-policy` |
| `address-full-policy` | **Từng address** | `PAGE`, `BLOCK`, `FAIL`, `DROP` | Quy định hành vi khi ngưỡng address **hoặc global** tác động lên address |
| `page-size-bytes` | **Từng address** | Kích thước **mỗi page file** | Chỉ điều khiển cách paging phân chia file, **không phải** tổng quota đĩa |
| `page-limit-bytes` / `page-limit-messages` | **Từng address trong paging** | Giới hạn lượng paging theo cơ chế hỗ trợ | Dùng với `page-full-policy` nếu muốn giới hạn phần dữ liệu sau khi đã page |
| `max-disk-usage` | **Toàn broker** | Phần trăm dung lượng đĩa đã sử dụng; `-1` để tắt | Khi disk scan cho thấy phần trăm sử dụng đạt ngưỡng |
| `min-disk-free` | **Toàn broker** | Số byte dung lượng còn trống; `-1` để tắt | Khi free space xuống dưới mức yêu cầu; **ưu tiên hơn** `max-disk-usage` nếu cùng cấu hình |
| `disk-scan-period` | **Toàn broker** | Millisecond | Tần suất broker quét trạng thái dung lượng đĩa |
| `disk-full-policy` | **Từng address** theo version hỗ trợ | `BLOCK`, `FAIL`, `DROP` | Hành vi khi **giới hạn đĩa toàn broker** bị chạm |

**Mặc định cần nhớ theo tài liệu 2.57.0:** `global-max-size` mặc định khoảng **50% `-Xmx`**; `global-max-messages=-1`; `max-disk-usage=90` (phần trăm); `min-disk-free=-1`; `disk-scan-period=5000 ms`; `disk-full-policy=BLOCK`. Các default tại **từng address** còn phụ thuộc wildcard `<address-setting match="#">` trong file mà instance tạo ra — không được đoán chỉ từ default trong manual.

### Hai quy tắc về đơn vị và phạm vi

**Quy tắc 1 — Tên giống nhau không có nghĩa cộng dồn cùng phạm vi.** Nếu cấu hình:

~~~xml
<address-setting match="orders.#">
    <max-size-bytes>10485760</max-size-bytes>
</address-setting>
~~~

thì **mỗi address** khớp `orders.#` có ngưỡng 10 MiB, không có một quota 10 MiB dùng chung cho *tất cả* các address dưới wildcard. Khi cần trần dùng chung cho nhiều address, dùng giới hạn global.

**Quy tắc 2 — Bộ nhớ message không phải heap tổng thể.** `global-max-size` bảo vệ ngân sách **in-memory messages** được broker theo dõi, không giới hạn toàn bộ heap, số thread, network buffer, client prefetch hay lượng dữ liệu persistence trên disk. Broker vẫn cần cấu hình `-Xmx` phù hợp, quan sát RSS/GC và có headroom cho chức năng khác.

## 3. Giới hạn toàn broker: ngăn nhiều address cùng làm tràn ngân sách memory

### 3.1. `global-max-size` và `global-max-messages`

Giả sử broker chạy JVM với `-Xmx=512 MiB`. Nếu không đặt `global-max-size`, theo default 50% broker tính ngân sách message memory xấp xỉ **256 MiB**. Có thể ấn định explicit:

~~~xml
<!-- Đặt trong phần <core> của ARTEMIS_INSTANCE/etc/broker.xml -->
<global-max-size>67108864</global-max-size>     <!-- 64 MiB -->
<global-max-messages>50000</global-max-messages>
~~~

**Lưu ý XML:** Đây là hai thẻ **con trực tiếp của `<core>`**, không nằm trong `<address-settings>`. Không thêm một `<core>` thứ hai vào file có sẵn.

Khi cả hai được bật, ngưỡng nào đạt trước sẽ khiến broker áp dụng chính sách đầy của address đang nhận message. Ví dụ:

- Có 45.000 message rất nhỏ nhưng tổng mới 30 MiB: chưa chạm ngưỡng cấu hình trên.
- Có 20.000 message tổng vượt 64 MiB: tác động từ `global-max-size` dù chưa chạm 50.000 message.
- Có 50.000 message nhỏ tổng dưới 64 MiB: ngưỡng count có thể tác động trước.

Đây là mô hình để đọc cấu hình; cách Artemis ước tính memory per-message, reference của multicast và in-flight credits làm mốc thực tế không nhất thiết trùng với phép tính `body.length × count`.

### 3.2. Toàn broker đầy thì từng address xử lý thế nào?

**Global limit không mang một “global-full-policy” riêng trong các ví dụ trên.** Khi ngưỡng chung được chạm, broker áp dụng `address-full-policy` **của address liên quan**:

- Address A cấu hình `PAGE` → được chuyển sang paging dù bản thân A chưa chạm `max-size-bytes`.
- Address B cấu hình `FAIL` → lệnh gửi mới có thể bị từ chối.
- Address C cấu hình `BLOCK` → producer bị backpressure.

Vì vậy một địa chỉ có `max-size-bytes=-1` không mặc nhiên thoát mọi hạn chế: ngưỡng global vẫn có thể kích hoạt chính sách address của nó.

**Không dùng global-max-size như cách tránh disk full.** `PAGE` vẫn có thể tiếp tục chuyển message xuống page files trên disk. Global memory limit bảo vệ memory, còn ngưỡng disk là lớp bảo vệ riêng.

### 3.3. Khi nào cần đặt explicit thay vì dùng mặc định?

Đặt explicit nếu:

- Nhiều nhóm cùng sử dụng một broker và phải tránh address A/B chiếm quá nhiều tổng message memory.
- Hệ thống chạy trong container có ngân sách heap/GC được kiểm soát, cần dự báo tác động của tăng `-Xmx`.
- Bạn cần một ngưỡng đo/truy vết cố định qua các lần nâng cấp và thay cấu hình JVM.

Mặt trái: đặt global quá thấp có thể khiến **nhiều address bị paging/block/fail đồng loạt**, ngay cả khi dung lượng ổ đĩa còn nhiều. Vì vậy phải đo address memory usage, paging, latency và throughput ở tải đỉnh.

## 4. Giới hạn riêng từng address: PAGE, BLOCK, FAIL hay DROP?

`max-size-bytes` và `max-size-messages` được cấu hình dưới `<address-settings>` và áp dụng theo wildcard. Cả hai đo **ngưỡng của một address**, không phải quota vật lý chung cho tất cả queue.

### 4.1. So sánh chính sách

| `address-full-policy` | Khi address/global chạm ngưỡng | Có giữ lại message mới? | Thường phù hợp khi |
|---|---|---|---|
| **PAGE** | Chuyển message mới sang cơ chế paging để hạn chế memory | Có thể **giữ trên storage**, nếu disk còn chỗ và cấu hình hợp lệ | Công việc cần backlog bền vững, chấp nhận I/O và độ trễ cao hơn |
| **BLOCK** | Giảm/ngưng cấp credits hoặc chặn producer theo giao thức | Không nhận thêm vượt chính sách cho đến khi có tài nguyên | Ưu tiên backpressure thay vì tăng backlog |
| **FAIL** | Từ chối message mới và trả lỗi cho client | Message bị từ chối **không được lưu** | Muốn fail-fast; ứng dụng có retry budget và idempotency |
| **DROP** | Bỏ message mới khi ngưỡng chạm | **Không** | Chỉ khi mất mẫu telemetry/message là chấp nhận được |

**Không dùng `DROP` cho đơn hàng, thanh toán hoặc tác vụ bắt buộc**, vì client có thể không nhận được thông báo lỗi tương đương `FAIL`. Với `FAIL`, lỗi có thể xuất hiện khi `send()` hoặc `commit()` tùy client và transaction; ứng dụng cần xử lý trạng thái không chắc chắn khi network timeout.

### 4.2. Ví dụ hai address khác policy

Đặt mảnh cấu hình sau **trong section `<address-settings>` hiện có**:

~~~xml
<address-setting match="lab.flow.page">
    <max-size-bytes>2097152</max-size-bytes>
    <max-size-messages>10000</max-size-messages>
    <page-size-bytes>1048576</page-size-bytes>
    <address-full-policy>PAGE</address-full-policy>
    <disk-full-policy>BLOCK</disk-full-policy>
</address-setting>

<address-setting match="lab.flow.fail">
    <max-size-bytes>2097152</max-size-bytes>
    <max-size-messages>10000</max-size-messages>
    <address-full-policy>FAIL</address-full-policy>
    <disk-full-policy>BLOCK</disk-full-policy>
</address-setting>
~~~

Trong đó:

- `2097152` byte = **2 MiB** message-memory threshold **cho mỗi address**.
- `10000` là ngưỡng count bổ sung; ngưỡng byte/count nào chạm trước sẽ kích hoạt policy.
- `page-size-bytes=1048576` là page file khoảng **1 MiB**, **không** giới hạn tổng page files xuống 1 MiB.
- Hai address có hành vi khác nhau vì `address-full-policy` khác nhau, dù broker global limit là một ngân sách dùng chung.
- `disk-full-policy=BLOCK` là **chính sách đối với ngưỡng đĩa**, không phải chính sách khi address chạm 2 MiB. Thẻ này được tài liệu Artemis hiện hành hỗ trợ; trên broker cũ cần kiểm tra version trước khi chép vào XML.

**Đừng nhầm threshold với hard cap chính xác từng byte.** Core producer có credit/window và message in-flight; AMQP credit đếm theo message, do đó usage thực tế có thể tạm vượt ngưỡng trước khi backpressure được áp dụng. Hãy quan sát broker metrics, không viết một test khẳng định “message thứ 33 phải thất bại” chỉ dựa trên kích thước body.

### 4.3. Multicast có nhiều queue: một subscriber chậm ảnh hưởng các subscriber khác

Một address multicast có thể gắn nhiều subscription queues. Artemis theo dõi message và reference của các queue; nếu **một subscription rất chậm**, message chưa ACK của nó có thể tiếp tục giữ dữ liệu và khiến **cả address** phải paging. Vì vậy:

- `max-size-bytes` tại address **không** cấp một quota độc lập cho từng subscription queue.
- Một slow subscriber có thể làm tăng I/O paging cho các queue/consumer nhanh dù chúng thường không backlog.
- Khi cần cô lập tài nguyên và SLA khác nhau, cân nhắc tách address, subscription policies hoặc broker; không chỉ tăng page-size mãi.

### 4.4. Giới hạn riêng phần dữ liệu đã paging

Khi chọn `PAGE`, có thể cân nhắc các thiết lập `page-limit-bytes`, `page-limit-messages` và `page-full-policy` ở các version hỗ trợ:

~~~xml
<!-- Ví dụ tách riêng, chỉ thêm khi đã kiểm chứng trên broker/version. -->
<address-setting match="lab.flow.page">
    <max-size-bytes>2097152</max-size-bytes>
    <page-size-bytes>1048576</page-size-bytes>
    <address-full-policy>PAGE</address-full-policy>
    <page-limit-bytes>10485760</page-limit-bytes>
    <page-full-policy>FAIL</page-full-policy>
</address-setting>
~~~

Theo tài liệu Artemis, `page-limit-bytes` liên quan tới số page files sau quy đổi theo `page-size-bytes`; nó không đơn giản là “tổng kích thước tất cả file broker không được vượt chính xác 10 MiB”. Đây là **lớp giới hạn riêng cho paging**, không thay thế ngưỡng đĩa toàn broker. Trong lab chính bên dưới **không bật page limit** để quan sát riêng tác động của `PAGE` và `FAIL`.

## 5. Ngưỡng dung lượng đĩa: đừng xem PAGE là vô hạn

### 5.1. `max-disk-usage` và `min-disk-free`

Đối với broker persistence dùng filesystem, page files, message journal, bindings và large messages đều cần storage. Artemis có cơ chế quét định kỳ nhằm giảm nguy cơ lấp đầy disk.

Đặt trong phần `<core>` của `broker.xml`:

~~~xml
<max-disk-usage>85</max-disk-usage>
<disk-scan-period>5000</disk-scan-period>
~~~

Cấu hình trên hướng đến mục tiêu broker bắt đầu bảo vệ khi disk sử dụng khoảng **85%** theo cách broker giám sát, với thời gian kiểm tra khoảng **5 giây**. Đây là con số minh họa, không phải default hay khuyến nghị cho mọi volume. Với một filesystem dung lượng 500 GiB, mức 85% là khoảng 425 GiB đã dùng; phần trống 75 GiB còn lại là headroom lý thuyết trước khi đi tới đầy 100%.

Thay vì phần trăm, phiên bản Artemis hỗ trợ có thể dùng **ngưỡng dung lượng trống tuyệt đối**:

~~~xml
<!-- Chọn một chiến lược ngưỡng đĩa; chỉ dùng trên bản có hỗ trợ. -->
<min-disk-free>20GB</min-disk-free>
<disk-scan-period>5000</disk-scan-period>
~~~

**Nếu cùng cấu hình cả `max-disk-usage` và `min-disk-free`, `min-disk-free` được ưu tiên** theo manual hiện hành. Do đó không nên đặt cả hai rồi suy rằng broker đồng thời áp dụng quy tắc khắt khe hơn của hai ngưỡng. Chọn và kiểm chứng một chính sách rõ ràng.

### 5.2. Ngưỡng đĩa khác ngưỡng address ở đâu?

Khi `lab.flow.page` đạt 2 MiB:

- Nếu `address-full-policy=PAGE`, Artemis bắt đầu paging; storage tiếp tục tăng nếu producer nhanh hơn consumer.
- Nếu disk tổng thể chạm `max-disk-usage` hoặc `min-disk-free`, **ngưỡng disk** bắt đầu tác động.
- Khi `disk-full-policy=BLOCK`, broker chặn producer để bảo vệ storage **kể cả khi address vẫn đang đặt PAGE**.

Tương tự, `lab.flow.fail` có thể bị FAIL do chạm 2 MiB address; nhưng nếu chưa chạm ngưỡng address mà disk đã vượt mức cho phép, nó sẽ chịu **disk-full-policy=BLOCK**. Hai policy này phục vụ **hai nguyên nhân khác nhau**.

**Vấn đề recovery:** Khi disk policy BLOCK, bạn cần giảm việc phát message, xử lý backlog đã lưu, tăng dung lượng volume hoặc dọn tài nguyên **theo runbook an toàn**. Không xóa thủ công page/journal files khi broker đang chạy để “giải tỏa” vì có thể phá trạng thái bền vững.

### 5.3. `disk-full-policy` và khả năng của giao thức

Trong tài liệu Artemis hiện hành, `disk-full-policy` là **address-setting** có ba lựa chọn:

- `BLOCK` (mặc định): tạo backpressure đối với client có hỗ trợ.
- `FAIL`: từ chối message mới, producer thấy lỗi.
- `DROP`: bỏ message mới, chỉ hợp lý với dữ liệu mất được.

**Giao thức không nhất thiết hỗ trợ backpressure giống nhau.** Với client dùng STOMP — giao thức không có credit flow-control tương đương Core/AMQP — broker có thể ném lỗi và đóng kết nối thay vì chờ producer vô thời hạn. Vì vậy không ghi một runbook rằng mọi client chắc chắn sẽ bị “treo đến khi disk còn chỗ”. Hãy test đúng client/protocol/version.

### 5.4. Khi nào quét đĩa không cứu được dữ liệu?

- `disk-scan-period` nghĩa là kiểm tra **định kỳ**, không phải giám sát từng byte ghi. Một spike lớn có thể làm đầy disk trong khoảng giữa hai lần scan.
- Volume có thể bị chiếm bởi **process khác**, snapshot, WAL, log hoặc filesystem metadata; phần còn trống theo broker phải có dự phòng thực tế.
- Dữ liệu journal/large-message/paging có thể nằm ở các mount khác nhau; cần kiểm tra filesystem broker **đang giám sát thực tế** theo cấu hình và version.
- Việc đĩa hết chỗ hoàn toàn vẫn có thể gây shutdown/lỗi storage. Disk threshold là lớp bảo vệ chủ động, **không phải** bảo đảm rằng hardware/volume không bao giờ đầy.

Trong production, tạo cảnh báo ở ngưỡng **thấp hơn** giới hạn cứng, ví dụ cảnh báo khi còn 20% free nhưng broker mới BLOCK khi còn 15% (phần trăm chỉ minh họa). Nếu sử dụng `min-disk-free`, cảnh báo nên đo dung lượng trống tuyệt đối và **tốc độ tăng disk usage** để dự báo thời gian cạn.

## 6. Cấu hình lab hoàn chỉnh về **vị trí** các thiết lập

Ví dụ dưới là **các mảnh cần đặt vào `ARTEMIS_INSTANCE/etc/broker.xml` đang có**. Không thay cả file; giữ nguyên thẻ gốc, namespace, acceptors, security, journal và các address khác. Chỉ thêm mục chưa tồn tại hoặc sửa mục tương ứng, tránh section trùng.

### 6.1. Các tham số cấp broker

Đặt trực tiếp bên trong `<core>`:

~~~xml
<global-max-size>67108864</global-max-size>
<global-max-messages>50000</global-max-messages>
<max-disk-usage>85</max-disk-usage>
<disk-scan-period>5000</disk-scan-period>
~~~

**Yêu cầu an toàn trước khi thử:** Xác minh filesystem của broker hiện **chưa vượt ngưỡng 85%**. Nếu đã vượt, policy có thể chặn ngay, khiến thử nghiệm address FAIL/PAGE không phản ánh chính sách address. Không tự chọn một ngưỡng thấp hơn mức disk đang dùng trên máy có dữ liệu thật.

### 6.2. Tạo hai anycast queue

Trong section `<addresses>`:

~~~xml
<address name="lab.flow.page">
    <anycast>
        <queue name="lab.flow.page">
            <durable>true</durable>
        </queue>
    </anycast>
</address>

<address name="lab.flow.fail">
    <anycast>
        <queue name="lab.flow.fail">
            <durable>true</durable>
        </queue>
    </anycast>
</address>
~~~

Cấu hình anycast giúp đo **một queue nhận một bản message**; tránh có thêm multicast subscriptions khiến address memory/paging khó giải thích. Consumer chưa chạy, queue có thể tích backlog theo policy.

### 6.3. Áp dụng hai policy riêng

Trong section `<address-settings>`:

~~~xml
<address-setting match="lab.flow.page">
    <max-size-bytes>2097152</max-size-bytes>
    <max-size-messages>10000</max-size-messages>
    <page-size-bytes>1048576</page-size-bytes>
    <address-full-policy>PAGE</address-full-policy>
    <disk-full-policy>BLOCK</disk-full-policy>
</address-setting>

<address-setting match="lab.flow.fail">
    <max-size-bytes>2097152</max-size-bytes>
    <max-size-messages>10000</max-size-messages>
    <address-full-policy>FAIL</address-full-policy>
    <disk-full-policy>BLOCK</disk-full-policy>
</address-setting>
~~~

Khi broker version cũ chưa hỗ trợ `disk-full-policy`, **đừng sửa tên thẻ theo phỏng đoán**: xem reference đúng release và dùng chính sách disk được hỗ trợ. Cấu hình thử nghiệm ở đây dựa trên tài liệu Artemis 2.57.0.

### 6.4. Quyền truy cập

Nếu broker bật security, account producer cần quyền `send` và consumer cần quyền `consume` trên hai address. Ví dụ tại section `<security-settings>` hiện hữu:

~~~xml
<security-setting match="lab.flow.#">
    <permission type="send" roles="flow-lab"/>
    <permission type="consume" roles="flow-lab"/>
</security-setting>
~~~

Role phải được khai báo trong cơ chế xác thực của instance. Trong production nên tách quyền producer, consumer và operator, không cấp quyền quản trị/tạo/xóa queue nếu không cần. Sau khi chỉnh cấu hình trong lab, **restart broker rồi kiểm tra startup logs và management** để chắc chắn các setting đã được nạp.

## 7. Java/JMS thực hành: tạo backlog, quan sát PAGE và FAIL

### 7.1. Điều kiện

Ví dụ dùng Java 17, `jakarta.jms.*` và Artemis Jakarta client tương thích với broker. Phần này chỉ kiểm chứng logic qua **Artemis Core/JMS client**, không giả định ActiveMQ Classic hỗ trợ cùng cấu hình XML.

POM tối thiểu:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <artemis.version>2.57.0</artemis.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.apache.activemq</groupId>
        <artifactId>artemis-jakarta-client</artifactId>
        <version>${artemis.version}</version>
    </dependency>
</dependencies>
~~~

Chọn đúng version client/JDK/broker đang chạy và cấu hình kết nối. Ví dụ sử dụng `tcp://127.0.0.1:61616`; export biến môi trường `ARTEMIS_USER`, `ARTEMIS_PASSWORD` trong môi trường lab.

### 7.2. Chương trình gửi và drain

Lớp Java dưới có hai mode:

- `send page <runId> <count>` hoặc `send fail <runId> <count>`: gửi tối đa `count` message khoảng 64 KiB body, từng message gửi **persistent** và commit riêng; log mỗi lần commit và dừng nếu broker từ chối.
- `drain page <runId> <count>` hoặc `drain fail <runId> <count>`: nhận/commit lần lượt message có cùng `runId` để giảm backlog, giúp broker thoát paging/block nếu điều kiện khác cho phép.

~~~java
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public final class FlowLimitsLab {
    private static final String URL = "tcp://127.0.0.1:61616";
    private static final String PAGE_QUEUE = "lab.flow.page";
    private static final String FAIL_QUEUE = "lab.flow.fail";

    public static void main(String[] args) throws Exception {
        if (args.length != 4 ||
                !("send".equals(args[0]) || "drain".equals(args[0])) ||
                !("page".equals(args[1]) || "fail".equals(args[1])) ||
                !args[2].matches("[A-Za-z0-9_-]{1,40}")) {
            usage();
            return;
        }

        int count = Integer.parseInt(args[3]);
        if (count < 1 || count > 256) {
            throw new IllegalArgumentException("count phải từ 1..256");
        }

        String user = env("ARTEMIS_USER");
        String password = env("ARTEMIS_PASSWORD");
        String queueName =
            "page".equals(args[1]) ? PAGE_QUEUE : FAIL_QUEUE;

        ActiveMQConnectionFactory factory =
            new ActiveMQConnectionFactory(URL);

        try (JMSContext context = factory.createContext(
                user, password, JMSContext.SESSION_TRANSACTED)) {
            Queue queue = context.createQueue(queueName);

            if ("send".equals(args[0])) {
                send(context, queue, args[2], count);
            } else {
                drain(context, queue, args[2], count);
            }
        }
    }

    private static void send(
            JMSContext context, Queue queue, String runId, int count)
            throws Exception {

        String payload = "X".repeat(64 * 1024);
        var producer = context.createProducer()
            .setDeliveryMode(DeliveryMode.PERSISTENT);

        int committed = 0;
        for (int seq = 1; seq <= count; seq++) {
            try {
                TextMessage message = context.createTextMessage(payload);
                String eventId = runId + "-" + seq;

                message.setStringProperty("runId", runId);
                message.setStringProperty("eventId", eventId);
                message.setIntProperty("seq", seq);

                producer.send(queue, message);
                context.commit();
                committed++;

                if (seq % 10 == 0 || seq == count) {
                    System.out.printf("COMMITTED=%d runId=%s%n",
                        committed, runId);
                }
            } catch (Exception failure) {
                try {
                    context.rollback();
                } catch (RuntimeException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                System.err.printf(
                    "SEND_FAILED seq=%d committedBeforeError=%d: %s%n",
                    seq, committed, failure);
                return;
            }
        }
    }

    private static void drain(
            JMSContext context, Queue queue, String runId, int limit)
            throws Exception {

        // runId chỉ có chữ/số/_/- nên có thể nhúng vào JMS selector.
        String selector = "runId = '" + runId + "'";
        JMSConsumer consumer = context.createConsumer(queue, selector);
        int done = 0;

        try {
            while (done < limit) {
                Message message = consumer.receive(1200);
                if (message == null) {
                    break;
                }

                try {
                    if (!(message instanceof TextMessage)) {
                        throw new IllegalArgumentException(
                            "Lab chỉ hỗ trợ TextMessage");
                    }
                    // Production: chỉ ACK sau side effect nghiệp vụ
                    // idempotent; lab chỉ ghi nhận eventId.
                    System.out.println(
                        "RECEIVE " +
                        message.getStringProperty("eventId"));
                    context.commit();
                    done++;
                } catch (Exception failure) {
                    context.rollback();
                    throw failure;
                }
            }
            System.out.println("DRAIN_COMMITTED=" + done);
        } finally {
            consumer.close();
        }
    }

    private static String env(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Thiếu biến " + key);
        }
        return value;
    }

    private static void usage() {
        System.out.println(
            "FlowLimitsLab send|drain page|fail <runId> <1..256>");
    }
}
~~~

**Vì sao không cố gửi tới khi đầy ổ đĩa?** Lab có ngưỡng `count <= 256` và message body khoảng 64 KiB, tức kích thước payload tối đa trong một lượt có giới hạn. Kích thước lưu thực tế gồm thêm metadata, journal/page overhead và có thể lớn hơn body. Với address `PAGE`, mục tiêu là quan sát **chuyển từ memory sang paging**, không phải kiểm tra giới hạn đĩa bằng cách làm cạn disk.

**Vì sao gửi commit từng message?** Một JMS transaction rất lớn có thể làm phép đo memory/paging khó hiểu do dữ liệu chưa commit và tương tác transaction. Gửi/commit riêng giúp quan sát ngưỡng ở từng bước; mã thật có thể batch transaction theo throughput/SLO.

**Chú ý khi lỗi ở `commit()`:** Nếu kết nối mất đúng lúc broker quyết định commit, producer có thể không biết chắc message đã được lưu. Việc gửi lại nên dùng cùng `eventId` ổn định; consumer phải idempotent. Log `committedBeforeError` chỉ đếm những lần client **đã nhận phản hồi commit thành công**.

## 8. Trình tự kiểm chứng từng lớp giới hạn

### 8.1. Ca A — Address PAGE

1. Dùng broker **lab riêng**, xác nhận disk usage thấp hơn ngưỡng `max-disk-usage` và queue `lab.flow.page` rỗng.
2. Chạy `FlowLimitsLab send page PAGE01 100` (chạy bằng IDE hoặc cấu hình Java của dự án).
3. Quan sát broker console: address `lab.flow.page` có thể chuyển sang **paging** khi message memory vượt khoảng 2 MiB; file trong paging directory có thể xuất hiện theo cơ chế page store.
4. Xác nhận sender tiếp tục commit các message trong khi page mode hoạt động, nếu disk/storage còn chỗ và broker không bị giới hạn khác.
5. Chạy `FlowLimitsLab drain page PAGE01 100`, kiểm tra queue count giảm; sau khi mọi reference cần thiết đã ACK, page files có thể được broker thu hồi theo thời gian.

**Điểm cần chứng minh:** `max-size-bytes=2 MiB` là ngưỡng **memory/paging**, không phải trần 2 MiB cho tổng message chưa tiêu thụ. Đừng xóa page files bằng tay; số file/nhịp xóa còn phụ thuộc cấu hình, batch và tốc độ broker.

### 8.2. Ca B — Address FAIL

1. Bắt đầu với queue `lab.flow.fail` rỗng.
2. Chạy `FlowLimitsLab send fail FAIL01 100`.
3. Khi address đạt ngưỡng 2 MiB (hoặc global 64 MiB nếu tải khác có ảnh hưởng), producer có thể thấy lỗi ở `send()`/`commit()`; chương trình log `SEND_FAILED` và không tiếp tục gửi trong lượt này.
4. Kiểm tra số message **đã được commit thành công** đang chờ trong queue; nhận/drain chúng bằng `FlowLimitsLab drain fail FAIL01 100`.
5. Nếu chưa thấy lỗi trong 100 message, xác minh threshold/policy đang được áp dụng, payload thực sự có kích thước và không có consumer đang drain; tăng count tối đa tới **256** trong lab đã kiểm soát tài nguyên.

Không kỳ vọng lỗi ở **đúng message thứ 33**: phép tính 2 MiB / 64 KiB không tính đến overhead, memory estimate, batching và credits. Nếu client dùng protocol khác, loại lỗi hoặc thời điểm nhận lỗi có thể khác.

### 8.3. Ca C — Global limit

Để kiểm chứng global riêng rẽ, không được chỉ nhìn hai address đều có ngưỡng 2 MiB: chúng có thể page/fail **trước khi** tổng message memory đạt 64 MiB.

Một phép thử tách biệt cần:

1. Tạo **môi trường lab khác** hoặc chọn thêm các address với giới hạn riêng đủ cao (không sửa queue production).
2. Đặt `global-max-size` thấp **nhưng phù hợp với heap/test load**, ví dụ 8 MiB, và address `PAGE` có `max-size-bytes` lớn hơn mức đó.
3. Phát message tới các address, theo dõi **aggregate address memory usage** và việc policy của address được kích hoạt dù một address riêng chưa đầy.
4. Xác nhận address mang `FAIL`, `BLOCK` hay `PAGE` có phản ứng theo **policy của chính nó** khi ngưỡng global tác động.

Đừng đặt `global-max-size` sát 0 trên broker thực đang phục vụ client. Thực hành có thể khiến tất cả address áp dụng policy sớm, dẫn đến nghẽn dịch vụ ngoài ý muốn.

### 8.4. Ca D — Disk threshold, không cần làm đầy đĩa thật

**Không kiểm thử bằng cách ghi file rác cho đến khi filesystem hết chỗ.** Việc đó có thể gây corruption journal, ảnh hưởng broker khác và dịch vụ host.

Một kế hoạch an toàn hơn:

1. Sử dụng **instance Artemis riêng trên volume thử nghiệm có quota rõ ràng**, không dùng dữ liệu thật.
2. Đo disk used/free thực tế và xác nhận mount broker đang dùng.
3. Đặt `max-disk-usage` hoặc `min-disk-free` phù hợp với volume test để có thể đạt ngưỡng **trước khi disk thật sự cạn**, sau đó reload/restart theo quy trình đã kiểm chứng.
4. Dùng producer có giới hạn số message; quan sát broker báo disk limit và client **BLOCK/FAIL** theo policy của version/protocol.
5. Giảm usage bằng **tiêu thụ/ACK message hợp lệ, dọn dữ liệu thông qua broker hoặc mở rộng volume**, không xóa file journal/page thủ công.
6. Xác minh producer phục hồi sau khi resource được giải phóng và metric trở lại dưới ngưỡng.

Nếu không có volume cô lập, **chỉ kiểm tra cấu hình và metric**, không cố kích hoạt disk-full trên laptop/workstation dùng chung. Với chính sách `BLOCK`, client có thể chờ; luôn đặt timeout/quy trình kết thúc test và không để producer treo vô hạn trong pipeline CI.

### Bảng kỳ vọng

| Tác nhân kích hoạt | Setting đang xét | Phản ứng đúng cần ghi |
|---|---|---|
| Address `lab.flow.page` vượt memory threshold | `max-size-bytes` + `PAGE` | Bắt đầu paging, producer vẫn có thể commit nếu storage còn đủ |
| Address `lab.flow.fail` vượt memory threshold | `max-size-bytes` + `FAIL` | Producer nhận lỗi, message bị từ chối không được lưu |
| Tổng message memory/count đạt global threshold | `global-max-*` | Mỗi address chịu `address-full-policy` của mình |
| Disk usage/free-space vượt ngưỡng | `max-disk-usage` / `min-disk-free` | Áp dụng `disk-full-policy`, không phải tự động bật PAGE |
| Consumer ACK backlog và giải phóng tài nguyên | Dưới ngưỡng đang có hiệu lực | Broker có thể ngừng paging/block theo trạng thái cập nhật; thời điểm phụ thuộc release/resource |

## 9. Chính sách kết hợp trong production

Một thiết kế thực tế thường có **ba vòng bảo vệ**:

~~~text
Layer 1: Address
  PAGE cho đơn hàng cần giữ backlog
  FAIL/BLOCK cho luồng cần backpressure
  Không dùng DROP cho dữ liệu không được mất

Layer 2: Global message memory
  global-max-size và/hoặc global-max-messages
  Giảm rủi ro nhiều address tích message vượt tổng ngân sách

Layer 3: Disk safety
  max-disk-usage hoặc min-disk-free
  disk-full-policy theo address
  Cảnh báo sớm + volume quota + auto-scaling/runbook có kiểm soát
~~~

### 9.1. Backlog có thể tăng mà memory ổn định

Giả sử producer phát 500 message/s và consumer ACK 300 message/s, với payload trung bình 4 KiB. Backlog tăng khoảng **200 message/s**, tương đương **0,78 MiB/s payload**; sau 10 phút khoảng **469 MiB payload** chưa kể metadata/page/journal overhead.

Nếu `PAGE` đang bật, broker có thể giữ memory ổn định gần ngưỡng address trong khi disk tiếp tục tăng. Nếu chỉ nhìn heap usage, bạn có thể không nhận ra volume sắp đầy. Do đó luôn theo dõi **queue age, backlog count và disk growth rate** song song.

### 9.2. Ưu tiên cảnh báo theo “thời gian đến khi hết chỗ”

Một cảnh báo chỉ kiểm tra “disk còn dưới 85%” có thể quá chậm khi incoming rate tăng mạnh. Nên bổ sung:

- **Current disk used/free** cùng ngưỡng broker đang áp dụng.
- **Tốc độ tăng storage** qua thời gian, ước tính thời gian còn lại.
- **Paging active** và page-file count/bytes, đặc biệt ở address nhiều multicast subscriptions.
- **Producer send/commit latency** p95/p99, số lỗi và thời gian bị BLOCK.
- **Queue oldest-message age**, ready/delivering count, enqueue/dequeue/ACK rate.
- **Global address-memory usage** so với `global-max-size` và tổng message count so với `global-max-messages`.
- **Nguồn gây áp lực**: phân address, queue, tenant và loại producer.

### 9.3. Khi producer bị BLOCK cần làm gì?

1. **Không** tăng memory/global/disk threshold vô điều kiện chỉ để hết alarm.
2. Xác định tầng gây nghẽn: address full, global message memory hay disk threshold.
3. Nếu do slow consumer: kiểm tra downstream DB/API, consumer count, prefetch, retry/DLQ, queue age.
4. Nếu do disk growth: ưu tiên tiêu thụ hợp lệ, thêm dung lượng hoặc giảm tốc producer; không tự xóa journal/paging.
5. Nếu do gửi sai message/tenant: chặn tại nguồn và điều tra auth/routing.
6. Nếu yêu cầu ứng dụng fail-fast thay vì treo, chọn `FAIL` **có chủ đích** cho luồng thích hợp và bảo đảm producer nhận/ghi nhận lỗi, có retry budget và idempotency.

### 9.4. Timeout và retry ở client

Khi Core/AMQP producer chịu backpressure, một lệnh `send` hoặc `commit` có thể đợi, tùy client/provider và cách xác nhận. Trong ứng dụng:

- Thiết lập **timeout tổng** cho một nghiệp vụ gửi, dùng connection/send/transaction timeout được provider hỗ trợ.
- Nếu retry sau timeout, giữ **eventId cố định** của cùng message nghiệp vụ; lần send trước có thể đã được broker commit nhưng client chưa biết chắc.
- Dùng circuit breaker/rate limiter khi broker đạt ngưỡng, tránh hàng nghìn producer cùng retry nóng.
- Phân biệt **FAIL do policy** với lỗi socket/TLS/auth để đưa ra hành động đúng.
- Đo success bằng **kết quả send/commit đã xác nhận**, không chỉ bằng số lời gọi hàm.

Không cho phép application âm thầm bỏ lệnh thanh toán chỉ vì policy `DROP`; với message quan trọng, chọn đường gửi và xác nhận có thể quan sát, kiểm chứng end-to-end.

## 10. Lỗi thường gặp và cách chẩn đoán

| Dấu hiệu | Nguyên nhân thường gặp | Cách xác minh |
|---|---|---|
| Producer bị chặn dù queue riêng còn rất ít message | Global limit đạt, hoặc disk limit đã chạm | Xem global memory/count, disk usage/free và policy của address |
| Queue có hơn 2 MiB dù `max-size-bytes=2 MiB` | Address đang `PAGE`, không phải hard disk quota; có overhead/in-flight credits | Kiểm tra paging state và total queue message count |
| Đã tăng `page-size-bytes` mà disk vẫn đầy | Page size chỉ là kích thước từng file | Xem backlog, page-file count, storage growth và disk threshold |
| Chỉ một slow topic subscriber làm tất cả chậm | Multicast address giữ references và phải paging do subscription chậm | Theo dõi queue/subscription riêng và address memory/paging |
| Policy `FAIL` mà producer không báo ngay | Async send/transaction/client acknowledgment; config chưa nạp | Kiểm tra `send/commit` outcome, client log, broker setting hiện hành |
| `max-disk-usage=85` nhưng broker BLOCK ở mức khác | Có `min-disk-free` nên nó được ưu tiên; mount/scan khác | Đọc cấu hình broker chạy, disk scan, đường dẫn dữ liệu |
| STOMP mất kết nối khi disk đầy thay vì chờ | Giao thức không hỗ trợ cùng cơ chế flow control | Xem broker logs, client protocol và `disk-full-policy` |
| Tăng `global-max-size` mà lỗi vẫn còn | Giới hạn address hoặc disk đang tác động, không phải global | Kiểm tra tầng có trigger thực tế |
| Thay `address-full-policy` không thấy tác dụng | Cấu hình trùng/wildcard match khác, reload chưa áp dụng | Console/JMX address settings, startup log và config reload |
| Tiến trình crash khi disk hết chỗ | Ngưỡng an toàn đặt sai, burst lớn trước kỳ scan hoặc mount khác đầy | Disk metrics/scan period, journal I/O errors, backup/restore plan |
| Client resend rồi consumer thấy message trùng | Commit outcome không chắc, producer retry | EventId ổn định, idempotent consumer và audit |
| Page files chưa biến mất ngay sau ACK | Page file có thể còn references, cleanup/depage theo chu kỳ | Kiểm tra tất cả queues/subscriptions, cursor và broker metrics |

## 11. Bài tập tự kiểm tra

1. Broker có 20 address; mỗi address được áp `max-size-bytes=10MiB` bằng wildcard. Tổng các address có bị giới hạn **chung** ở 10MiB không? Nên dùng setting nào để giới hạn toàn broker?
2. Khi `global-max-size` đạt ngưỡng nhưng address A chưa chạm `max-size-bytes`, `address-full-policy=FAIL` của A còn có hiệu lực không?
3. Vì sao `PAGE` có thể bảo vệ heap nhưng vẫn dẫn tới đầy disk? Lớp cấu hình nào ngăn nguy cơ đó?
4. Trong hai setting `max-disk-usage=85` và `min-disk-free=20GB`, setting nào được ưu tiên khi cùng có mặt theo Artemis hiện hành?
5. `page-size-bytes=1MiB` có giới hạn một queue chứa tối đa 1MiB dữ liệu không?
6. Với hàng đợi lệnh thanh toán, nên dùng `DROP` hay `FAIL/BLOCK/PAGE` khi address đầy? Điều gì cần có ở producer/consumer?
7. Nếu broker đang ở PAGE nhưng một subscriber multicast không ACK, tại sao các subscriber khác có thể bị tăng latency?
8. Producer Core và STOMP đều dùng `disk-full-policy=BLOCK`. Có thể khẳng định cả hai sẽ được chặn qua cùng một cơ chế credits không?
9. Tại sao test `FAIL` không nên yêu cầu “message thứ 33 phải ném exception” dù 2MiB / 64KiB xấp xỉ 32?
10. Nếu broker restart sau khi đội vận hành vô tình xóa một page file, có thể coi đó là cách an toàn để giải phóng disk không? Nêu nguy cơ và phương án thay thế.

**Đáp án định hướng:** (1) Không; mỗi address 10MiB, dùng `global-max-size`/`global-max-messages`; (2) Có, broker áp dụng address policy khi global đầy; (3) paging thêm file, phải có disk threshold và kiểm soát backlog; (4) `min-disk-free`; (5) Không, đó là kích thước page file; (6) tránh DROP, thiết kế ACK/retry/idempotency; (7) reference của subscription chậm giữ dữ liệu và làm address paging; (8) không, protocol khác khả năng flow-control; (9) overhead/credits/ước tính memory; (10) không, có thể hỏng dữ liệu broker, dùng tiêu thụ hợp lệ/expand volume và quản trị broker.

## 12. Checklist triển khai và tài liệu chính thức

Trước khi coi giới hạn đã hoạt động như kỳ vọng, kiểm tra đầy đủ:

- [ ] Broker/version và client protocol được ghi rõ; XML phù hợp schema phiên bản.
- [ ] `global-max-size`/`global-max-messages` đặt đúng **cấp `<core>`** và có số liệu giám sát tổng.
- [ ] `max-size-bytes`/`max-size-messages` cùng `address-full-policy` đặt đúng **address-setting**; wildcard được kiểm tra trên từng address.
- [ ] Nếu dùng `PAGE`, giám sát disk/page files và có giới hạn/bảo vệ storage riêng.
- [ ] `max-disk-usage` hoặc `min-disk-free` đặt với đủ headroom và hiểu ưu tiên giữa chúng; `disk-scan-period` thích hợp với tốc độ tăng storage.
- [ ] `disk-full-policy` thích hợp theo address và giao thức; không dùng `DROP` cho dữ liệu bắt buộc.
- [ ] Có metric send/commit latency, backpressure, queue age, paging và disk headroom; cảnh báo **trước** threshold cứng.
- [ ] Có runbook khi BLOCK/FAIL, không xóa file journal/page thủ công.
- [ ] Có bài thử tải và failure mode trên **instance cô lập**, không gây đầy volume thực.
- [ ] Producer dùng eventId ổn định và consumer idempotent khi retry sau kết quả commit không chắc chắn.

**Tài liệu chính thức đối chiếu (Artemis 2.57.0/latest tại thời điểm soạn):**

- [Artemis — Paging](https://artemis.apache.org/components/artemis/documentation/latest/paging.html): ngưỡng address/global, các chính sách và kiểm soát disk.
- [Artemis — Flow Control](https://artemis.apache.org/components/artemis/documentation/latest/flow-control.html): Core/AMQP producer credits, `BLOCK` và giới hạn overshoot.
- [Artemis — Address Settings](https://artemis.apache.org/components/artemis/documentation/latest/address-settings.html): `address-full-policy`, `disk-full-policy` và wildcard.
- [Artemis — Configuration Reference](https://artemis.apache.org/components/artemis/documentation/latest/configuration-index.html): `global-max-size`, `global-max-messages`, `max-disk-usage`, `min-disk-free`, `disk-scan-period`.
- [Artemis — Configuration Reload](https://artemis.apache.org/components/artemis/documentation/latest/config-reload.html): xem setting nào có thể reload thay vì giả định mọi thay đổi XML đều áp dụng tức thì.

**Kết luận:** Có ba câu hỏi phải luôn trả lời riêng khi điều tiết lưu lượng Artemis: **(1) toàn broker còn ngân sách message memory/count không? (2) address này áp dụng PAGE, BLOCK, FAIL hay DROP khi đầy? (3) volume còn đủ chỗ để journal/paging tiếp tục không?** `global-max-*` bảo vệ tổng tài nguyên message memory, `max-size-*` và `address-full-policy` điều phối từng address, còn `max-disk-usage`/`min-disk-free` cùng `disk-full-policy` bảo vệ storage. Chỉ khi đo được cả ba tầng và hành vi client thì cấu hình mới thực sự có ý nghĩa vận hành.
