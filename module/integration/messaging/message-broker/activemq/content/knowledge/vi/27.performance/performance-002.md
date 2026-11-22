# Tác động của kích thước thông điệp, persistence, TLS và giao dịch

> **Chương:** Hiệu năng  
> **Phạm vi:** Đo và lý giải hiệu năng Java/JMS khi dùng **Apache ActiveMQ Classic 6.x** hoặc **Apache Artemis 2.57.x** với queue bất đồng bộ. Bài tập trung đúng bốn biến: **kích thước message**, **persistent/non-persistent**, **TLS so với TCP thuần** và **giao dịch/commit theo batch**. Các ví dụ dùng JDK 17 và `jakarta.jms`; kết quả phải được đo trên broker, storage và mạng thực tế, không xem số liệu minh họa là benchmark đã chạy.

## 1. Một phép đo nhanh có thể trả lời sai câu hỏi

Một producer có thể báo `send()` đạt 50.000 message/giây trong khi broker mới chỉ nhận dữ liệu vào buffer, message chưa được flush xuống storage và consumer còn tồn hàng chục nghìn message. Một phép thử khác đạt 2.000 message/giây nhưng đã đợi xác nhận ghi bền vững mỗi lần gửi. So hai số này rồi kết luận một broker nhanh gấp 25 lần là **sai điều kiện đo**.

Trước khi benchmark phải trả lời rõ:

1. **Đơn vị công việc:** một message chứa bao nhiêu byte payload, bao nhiêu header và được mã hóa thành JMS `BytesMessage`/`TextMessage`/`ObjectMessage`?
2. **Điểm hoàn thành:** tính một lần gửi là thành công khi `send()` trả về, khi broker xác nhận, khi transaction `commit()` trả về, hay khi consumer hoàn tất nghiệp vụ?
3. **Bảo đảm dữ liệu:** `DeliveryMode.PERSISTENT` hay `NON_PERSISTENT`, broker dùng journal/KahaDB/JDBC, có sync và volume bền vững không?
4. **Tính tương đương của thí nghiệm:** TLS có thay mã hóa/handshake, giao dịch có thay số lần round trip và fsync, storage có chuyển sang paging/large-message path không?

```text
JMS producer             Network                Broker/store              Consumer
   │                       │                        │                        │
   ├─ encode payload       │                        │                        │
   ├─ send() ─────────────▶│ TLS/TCP bytes ────────▶│ append/store           │
   │                       │                        ├─ sync / commit?       │
   │◀─ confirmation? ──────┴────────────────────────┤                        │
   │                                                ├─ dispatch ───────────▶│
   │                                                │        process + ACK  │
   │                                                │◀──────────────────────┤
```

**Phân biệt bốn chỉ số:**

| Chỉ số | Định nghĩa hữu ích | Không đo được |
|---|---|---|
| `publishRate` (msg/s) | Số lời gọi gửi hoàn tất trong cửa sổ đo / giây | Không chứng minh đã xử lý hay ghi bền vững nếu send bất đồng bộ |
| `payloadRate` (MiB/s) | Tổng byte **payload** / thời gian; `1 MiB = 1.048.576 B` | Không phải tổng byte trên wire/disk vì có headers, framing và TLS |
| `send p99` (ms) | Phân vị 99% thời gian `send()`, trong cùng mode xác nhận | Với transaction, chưa bao gồm độ trễ `commit()` |
| `commit p99` (ms) | Phân vị 99% thời gian commit của từng batch | Không phải latency của từng message từ sản xuất đến tiêu thụ |
| `end-to-end p99` (ms) | Từ event tạo ra đến **side effect nghiệp vụ** thành công | Không suy được chỉ từ throughput producer |

Điểm cốt lõi: **throughput cao hơn có thể đổi lấy latency, độ bền, bộ nhớ hoặc lượng công việc cần retry lớn hơn**. Khi báo cáo phải ghi cùng lúc chi phí và điều kiện bảo đảm dữ liệu.

## 2. Kích thước message: đường cong không nhất thiết tuyến tính

Với cùng broker/network/producer, payload `256 B` và `256 KiB` không chỉ khác nhau ở số byte truyền. Message nào cũng có chi phí gần như cố định: khởi tạo đối tượng, JMS headers/properties, serialize/encode, bộ đệm, lock, dispatch, tracking/ACK. Khi payload lớn, chi phí copy bytes, TLS encryption, network và disk throughput dần chiếm ưu thế.

| Dải payload để thử | Nút thắt có khả năng | Chỉ số nên quan sát |
|---|---|---|
| 256 B – 1 KiB | Chi phí/message, gọi API, ACK/commit, scheduling | msg/s, CPU/messages, p99 `send` |
| 4 – 64 KiB | Copy/encode, buffer, network, write batching | MiB/s, GC allocation, socket throughput |
| 128 KiB – 1 MiB | Large-message path, disk/temp volume, paging, segmentation | p99, memory/RSS, disk throughput, page/large-message files |
| Nhiều MiB | Fragmentation, streaming, TLS records, buffer pressure | Time-to-first-byte, copy count, heap, network throughput |

Các dải là **bộ trường hợp đo đề xuất**, không phải ngưỡng bảo đảm cho mọi broker.

### 2.1. Artemis Core có đường xử lý large message riêng

Artemis Core client dùng tham số `minLargeMessageSize`; mặc định trong tài liệu 2.57.0 là **100 KiB (102.400 B)**. Message vượt ngưỡng được xử lý theo cơ chế **large message**, có thể chia fragment và lưu body tại thư mục `large-messages-directory` thay vì như một record nhỏ thông thường.

```text
Payload 64 KiB  -> thường đi đường regular message
Payload 256 KiB -> có thể đi đường large message/fragment
```

Vì thế benchmark với `64 KiB` và `256 KiB` có thể vượt **ranh giới cơ chế**, không thể ngoại suy throughput bằng tỉ lệ kích thước. Ngưỡng áp dụng cho **kích thước được mã hóa**, không chỉ số byte của String trước khi chuyển sang JMS. Với `TextMessage`, encoding cũng ảnh hưởng; dùng `BytesMessage` nếu muốn kiểm soát số byte body chính xác.

Ví dụ **client Artemis Core** giữ ngưỡng cố định giữa các lượt thử:

```text
tcp://broker.lab.example:61616?minLargeMessageSize=102400&compressLargeMessage=false
```

`compressLargeMessage=false` giúp không vô tình biến một payload dễ nén thành một phép thử network/disk khác. Nếu mục tiêu là đánh giá tính năng nén, phải tạo **một ma trận riêng** với payload nén được và không nén được, cùng CPU usage và compression level.

**Không áp `minLargeMessageSize` của Artemis vào ActiveMQ Classic**: Classic có cơ chế KahaDB/cursor/pending message và giới hạn transport khác. Các tên tham số giống nhau ở các sản phẩm không có nghĩa cùng code path.

### 2.2. Cấu trúc payload và khả năng nén là biến độc lập

Với hai message cùng `64 KiB`:

- Payload toàn ký tự `'A'` nén cực tốt.
- Payload byte giả ngẫu nhiên khó nén.
- Một `ObjectMessage` có overhead Java serialization và phụ thuộc classpath; không tương đương `TextMessage` JSON cùng số trường.

Khi muốn đo **kích thước**, cố định loại message (`BytesMessage`), metadata, kiểu dữ liệu và trạng thái compression. Khi muốn so JSON với binary/Protobuf, cần một phép thử riêng và giữ **cùng nội dung nghiệp vụ**, không so một JSON 5 KB với binary chỉ chứa 200 B mà kết luận chỉ do codec.

## 3. Persistence: giảm disk I/O không đồng nghĩa tăng hiệu năng miễn phí

Trong JMS, `DeliveryMode.PERSISTENT` yêu cầu provider xử lý message bền vững theo hợp đồng JMS, nhưng mức an toàn khi crash còn phụ thuộc cấu hình store, sync, topology HA, thời điểm xác nhận và thiết bị lưu trữ. `NON_PERSISTENT` cho phép broker không phải lưu bền vững message và có thể làm các phép gửi nhanh hơn, nhưng message có nguy cơ mất khi broker restart/failure.

| Khía cạnh | `PERSISTENT` | `NON_PERSISTENT` |
|---|---|---|
| Mục tiêu | Message cần sống qua sự cố theo hợp đồng provider/store | Dữ liệu mất được khi failure |
| Chi phí điển hình | Journal/KahaDB write, flush/commit, quota disk, compaction | Ít chi phí durable write hơn; vẫn tốn network/memory/dispatch |
| `send()` ngoài transaction | Thường chờ broker confirmation nếu client dùng mode gửi đồng bộ | Thường có thể gửi bất đồng bộ, khiến số đo `send()` trông nhanh hơn |
| Broker crash/restart | Có cơ sở recover nếu đã ghi và xác nhận theo sync policy | Không được dùng để bảo đảm khôi phục |
| Phù hợp | Đơn hàng, thanh toán, event chưa được bù trừ | Telemetry có thể bỏ, cache event tái tạo được |

**Muốn so persistence tương đối công bằng**, cần **cùng chính sách chờ xác nhận của producer**. Nếu persistent gửi đồng bộ còn non-persistent gửi fire-and-forget, phép thử đồng thời thay đổi **hai biến**: độ bền **và** mức chờ mạng. Phải ghi rõ hoặc cấu hình cả hai chế độ cùng chờ broker nhận.

### 3.1. ActiveMQ Classic: KahaDB và đồng bộ gửi

Theo tài liệu Classic, persistent send **ngoài transaction** mặc định đợi phản hồi broker; nonpersistent send thường đi async. Classic có các thuộc tính trên `ActiveMQConnectionFactory`:

```java
factory.setUseAsyncSend(false);
factory.setAlwaysSyncSend(true);
```

`setAlwaysSyncSend(true)` buộc cả hai delivery modes sử dụng synchronous send, phù hợp khi cố gắng cô lập tác động của persistence. **Nó không làm nonpersistent thành persistent.** Với production muốn giữ hành vi mặc định, phải benchmark thêm một bộ đo thực tế với `alwaysSyncSend=false` và báo cáo rõ chính sách confirmation khác nhau.

Nếu benchmark đụng KahaDB compaction, journal cleanup hoặc filesystem cache, latency có thể nhảy; cần quan sát disk util, `StorePercentUsage` và broker logs. Không tắt persistence của cả broker rồi tuyên bố “PERSISTENT nhanh hơn N lần”: khi `persistent=false` ở broker, mô hình durability đã đổi.

### 3.2. Artemis: journal sync và send guarantee

Đối với Artemis file journal, cấu hình tham chiếu trong **`broker.xml` đã có**:

```xml
<!-- Các phần tử này đặt trực tiếp trong <core>; không tạo <core> thứ hai. -->
<persistence-enabled>true</persistence-enabled>
<journal-sync-transactional>true</journal-sync-transactional>
<journal-sync-non-transactional>true</journal-sync-non-transactional>
<journal-datasync>true</journal-datasync>
```

Client Artemis Core có hai cờ:

```text
blockOnDurableSend=true
blockOnNonDurableSend=true
```

Trên **non-transacted JMSContext**, chúng yêu cầu `send` đợi broker trả phản hồi cho durable/non-durable messages; mặc định Artemis 2.57.0 là `true` cho durable và `false` cho non-durable. Để đo persistence dưới cùng chính sách chờ, đặt **cả hai true** trên URI client:

```text
tcp://broker.lab.example:61616?blockOnDurableSend=true&blockOnNonDurableSend=true
```

`journal-sync-transactional` quyết định việc flush record ở ranh giới commit; `journal-sync-non-transactional` điều khiển non-transacted send/ACK. **Không tắt hai cờ này chỉ để có cột throughput đẹp** mà không ghi thay đổi về durability. Ngay cả sync true vẫn cần volume đáng tin cậy, đúng HA topology và đo khả năng khôi phục.

### 3.3. Khi nào `send()` trả về là bằng chứng?

| Trường hợp | Điều `send()`/`commit()` đã xác nhận | Điều chưa chứng minh |
|---|---|---|
| Classic PERSISTENT, non-tx, synchronous | Broker đã xác nhận tiếp nhận/lưu theo cấu hình store | Consumer đã xử lý |
| Artemis PERSISTENT, non-tx, `blockOnDurableSend=true`, sync enabled | Broker đã phản hồi theo chính sách durable send | Thiết bị lưu trữ không bao giờ hỏng |
| NON_PERSISTENT, `send` synchronous | Broker đã nhận/xử lý theo mode non-durable | Message sống qua broker restart |
| Transacted send, trước `commit` | Message nằm trong transaction chưa hoàn tất | Message đã visible hay durable cho consumer |
| Transacted send, `commit` trả OK và sync true | Local JMS transaction được broker xác nhận theo store | Side effect database độc lập đã commit |
| Timeout trong `send`/`commit` | Kết quả **chưa rõ**; có thể broker đã xử lý nhưng response mất | Chắc chắn chưa gửi; không được retry bằng event ID mới |

## 4. TLS: thêm CPU/mã hóa, không nhất thiết thêm handshake mỗi message

TLS bảo vệ dữ liệu trên đường truyền, nhưng tiêu thụ CPU cho certificate verification, handshake, encryption/decryption, record framing và có thể thêm allocations/native calls. **Handshake chỉ xảy ra khi tạo hoặc tái thiết lập TLS connection**, không phải mỗi lần gửi message trên **một connection tái sử dụng**.

Nếu một benchmark tạo kết nối mới cho mỗi message thì kết quả TLS sẽ phản ánh chủ yếu **anti-pattern connection churn**, không phải chi phí mã hóa payload bình thường.

```text
TCP thuần             : connect -------- nhiều SEND trên cùng connection -------- close
TLS qua TCP           : connect + TLS handshake --- nhiều encrypted SEND -------- close
                                       ^                         ^
                                chi phí theo connection    chi phí mỗi byte/record
```

| Kiểu tải | TLS có thể tác động mạnh hơn ở đâu? |
|---|---|
| Nhiều connection mới/giây | Handshake, xác thực chứng chỉ, CPU và latency kết nối |
| Nhiều message rất nhỏ trên connection reuse | Phần tăng của framing, record và CPU/message, thường nhỏ so với sync/ACK |
| Message lớn, tốc độ cao | CPU mã hóa/giải mã, memory copy và giới hạn băng thông |
| Mạng RTT cao | Round trip của gửi đồng bộ/commit có thể lớn hơn chênh lệch chi phí mã hóa |
| CPU broker đã gần 100% | TLS có thể làm throughput giảm rõ dù disk còn rảnh |

**Không tắt TLS trong production để cải thiện benchmark.** Chạy cặp thử TCP/TLS trên môi trường **cô lập và được phê duyệt**; đánh giá lựa chọn production **với TLS bật** và giữ phiên bản TLS/cipher, cert chain, provider (JDK/OpenSSL) tương đương giữa các lần đo.

### 4.1. ActiveMQ Classic: SSL transport đúng namespace

Ví dụ **fragment** đặt bên trong `<broker>` hiện hữu của Classic `conf/activemq.xml`. Trong production, mật khẩu không đặt literal; dùng cơ chế secrets/environment substitution được phiên bản triển khai hỗ trợ và đã kiểm thử:

```xml
<!-- Bên trong <broker> đang có, không sao chép cả <broker>. -->
<sslContext>
    <sslContext keyStore="file:/secure/broker.p12"
                keyStoreType="PKCS12"
                keyStorePassword="REPLACE_IN_LAB_ONLY"/>
</sslContext>

<transportConnectors>
    <transportConnector name="ssl-benchmark"
        uri="ssl://0.0.0.0:61617?transport.needClientAuth=false"/>
</transportConnectors>
```

Đây là cấu hình **TLS một chiều** (server trình chứng chỉ). `needClientAuth=false` **không tắt xác thực tài khoản JMS**; quyền truy cập destination vẫn do broker security policy quản lý. Để **mTLS**, phải thêm truststore ở broker, cung cấp client certificate và bật `needClientAuth=true`.

Client dùng `org.apache.activemq.ActiveMQSslConnectionFactory` và `ssl://broker.lab.example:61617`; truststore phải chứa CA/certificate tin cậy và tên host phải **khớp Subject Alternative Name (SAN)**. Classic hỗ trợ hostname verification phía client; **không** đặt `verifyHostName=false` chỉ để test kết nối thành công.

### 4.2. Artemis Core: Netty acceptor TLS

Artemis `broker.xml` có thể thêm một acceptor riêng trong `<acceptors>` hiện hữu:

```xml
<acceptor name="core-tls-benchmark">tcp://0.0.0.0:61617?protocols=CORE;sslEnabled=true;keyStorePath=/secure/broker.p12;keyStoreType=PKCS12;keyStorePassword=REPLACE_IN_LAB_ONLY;needClientAuth=false</acceptor>
```

Trong URI **acceptor Artemis**, dùng `;` ngăn cách tham số. Trong URI **client Java**, dùng `&` như query string:

```text
tcp://broker.lab.example:61617?sslEnabled=true&verifyHost=true&blockOnDurableSend=true&blockOnNonDurableSend=true
```

Ứng dụng Artemis có thể cấp truststore thông qua `javax.net.ssl.trustStore`, `javax.net.ssl.trustStorePassword` và `javax.net.ssl.trustStoreType=PKCS12` của JVM; giữ chúng như secrets triển khai và không in trong log. Mã Java ở mục 7 cho thấy cấu hình truststore từ environment vào **tiến trình benchmark chuyên dụng** trước khi tạo factory.

**Đừng đưa keyStorePassword thật vào URI hay Git.** `REPLACE_IN_LAB_ONLY` là placeholder bắt buộc thay trong môi trường lab, **không** là mật khẩu đề nghị dùng. Cần quản lý chứng chỉ, xoay vòng, quyền file và chính sách cipher an toàn. Không bật `trustAll=true` hoặc bỏ verify hostname để làm số liệu “đẹp”.

## 5. Transaction: lợi ích của batch commit và chi phí rollback

Gửi persistent message **ngoài transaction** theo mode đồng bộ có thể đòi một vòng đợi xác nhận trên mỗi send. Khi gom `N` send trong một **transacted JMS Session**, lệnh `send` tạo các operation thuộc transaction; **`commit()` là ranh giới xác nhận chung** và là lúc journal phải flush transaction theo cấu hình.

```text
Không transaction, PERSISTENT + sync:
    send#1 -> wait broker
    send#2 -> wait broker
    send#3 -> wait broker

Transaction, batch=3:
    send#1 ─┐
    send#2 ─┼─ staged in same JMS Session
    send#3 ─┘
    commit -> wait broker / transaction durability
```

### 5.1. Phân tích độ trễ trên mỗi message

Một mô hình định tính cho batch `N` message:

\[
\text{time/batch} \approx N \cdot C_{\text{encode+transfer}} + C_{\text{commit round-trip+sync}}
\]

Suy ra phần chi phí commit được phân bổ theo message xấp xỉ:

\[
\text{commit overhead/message} \approx \frac{C_{\text{commit}}}{N}
\]

Đây **không phải mô hình hiệu năng chính xác**: network pipelining, lock, journal batching, payload size và storage contention làm chi phí không tuyến tính. Tuy nhiên nó giải thích vì sao `batch=10` hoặc `100` có thể tăng throughput đáng kể với payload nhỏ.

| Batch size | Ưu điểm | Đánh đổi |
|---|---|---|
| `1` | Ranh giới commit/rollback nhỏ, dễ xác định message nào thành công | Nhiều commit, latency sync cao |
| `10` | Ít commit hơn, thường tăng msg/s | Mất một batch khi rollback; message chờ commit lâu hơn |
| `100` | Phân bổ chi phí commit tốt nếu storage/network là bottleneck | Nhiều message chưa commit, tail latency tăng và retry nhiều hơn |
| `1000` | Có thể tăng throughput ở workload phù hợp | Bất lợi cho memory, failover/replay, fairness và giới hạn SLA |

**Với consumer**, transaction cũng có thể batch ACK nhưng phải cân nhắc **side effect bên ngoài**: nếu commit JMS của một batch thất bại, cả batch có thể redeliver; callback xử lý DB/HTTP phải idempotent. Không dùng commit theo 100 message nếu SLA đòi xử lý và xác nhận riêng từng message.

### 5.2. Không gộp hai khái niệm “transaction” và “batch”

`batch=0` trong mã lab ở mục 7 nghĩa là **không dùng JMS transaction**. `batch=1` là **một transaction cho mỗi message**. Khi so `0` với `1`, ta đã thay đổi **ngữ nghĩa giao dịch**, không chỉ số message/batch. Để đo riêng **kích thước batch**, so `1`, `10`, `100`, giữ mọi điều kiện khác bất biến.

## 6. Thiết kế ma trận benchmark bốn biến

### 6.1. Cấu hình cố định trước khi đo

Trên một **broker lab**, tạo queue **`lab.performance.factors`** riêng và không có dữ liệu nghiệp vụ. Dùng cùng Java/JVM, cùng RAM/CPU quota, NIC, broker version, journal/volume, policy memory/paging, producer count, consumer count, định dạng `BytesMessage` và payload không nén. Cho consumer chạy đồng thời để tránh bài thử dần chuyển sang **benchmark backlog/paging**.

Với Artemis, có thể provision queue:

```xml
<!-- Fragment trong <addresses> hiện có. -->
<address name="lab.performance.factors">
    <anycast>
        <queue name="lab.performance.factors"/>
    </anycast>
</address>
```

Với Classic, queue tương ứng:

```xml
<!-- Fragment trong <destinations> hiện có. -->
<queue physicalName="lab.performance.factors"/>
```

**Mỗi lượt đo bắt đầu ở một queue sạch hoặc một queue lab độc lập**. Không purge bất kỳ queue nào có message không thuộc run đó; ghi `runId` trong JMS property và chỉ chạy các consumer lab. Với Artemis, giữ địa chỉ không thay đổi `address-full-policy` hoặc `max-size-bytes` giữa các lượt; với Classic giữ nguyên `systemUsage` và destination policy. Nếu gặp paging/flow control, báo cáo như một **workload khác** hoặc giảm số lượng/backlog, không tùy tiện tăng RAM rồi so với kết quả trước.

### 6.2. Thí nghiệm thay một biến tại một thời điểm

| Thí nghiệm | Body size | Mode | TLS | Producer transaction batch | Mục đích |
|---|---:|---|---|---:|---|
| A0 — baseline | 4 KiB | Persistent | Tắt trong lab | 0 (non-tx) | Mốc throughput với synchronous send |
| A1 – A4 | 256 B / 1 KiB / 64 KiB / 256 KiB | Persistent | Tắt | 0 | Tác động kích thước, gồm ranh giới large message Artemis |
| B1 | 4 KiB | Non-persistent | Tắt | 0 | So chi phí persistence **với cùng sync-send confirmation** |
| C1 | 4 KiB | Persistent | Bật | 0 | Chênh lệch do TLS khi dùng connection reuse |
| D1 – D3 | 4 KiB | Persistent | Tắt | 1 / 10 / 100 | Tác động kích thước JMS transaction batch |

Đừng so số liệu A0 của Classic với C1 của Artemis để đánh giá riêng TLS. Muốn so sản phẩm, phải tạo **một ma trận hoàn chỉnh trên từng broker** và ghi khả năng tương thích, journal type, storage cùng cấu hình khách quan.

**Một lượt đo có kiểm soát:**

1. Warm-up JVM/JIT, TLS session và file journal bằng **runId/queue lab riêng**; loại bỏ giai đoạn chuẩn bị khỏi kết quả đo chính.
2. Kiểm tra broker không còn backlog cũ, ổ đĩa có đủ dung lượng, consumer sẵn sàng, không có job compaction ngoài kế hoạch.
3. Chạy ít nhất 3–5 lượt mỗi cấu hình, tráo thứ tự thử để giảm ảnh hưởng nhiệt độ/GC/cache, lấy median throughput và p95/p99.
4. Ghi **cả producer và consumer**, broker queue depth, disk IOPS/latency, CPU/GC, network throughput, TLS handshake failures.
5. Giữ nguyên cơ chế acknowledgment và **confirmation semantics** khi so các modes; đánh dấu riêng các phép thử khác guarantee.
6. Sau mỗi run, xác minh số message thuộc `runId` đã gửi/ACK, không có duplicate/loss do test harness.

**Lưu ý tải lớn:** `100.000 × 256 KiB ≈ 24,4 GiB payload`, chưa kể journal/metadata. Không chọn con số message theo cảm tính rồi làm đầy storage; giới hạn tổng payload hoặc chạy thí nghiệm ngắn có consumer theo kịp, giám sát capacity và dừng đúng ngưỡng.

## 7. Java 17/Jakarta JMS: benchmark bốn yếu tố bằng một harness

Chương trình dưới giữ nguyên **API JMS** cho cả hai broker, nhưng chọn đúng provider factory theo tham số. Hai dependency tương ứng có thể cùng có mặt trong **project lab chuyên dụng**; chương trình gọi class bằng tên đầy đủ để tránh trùng `ActiveMQConnectionFactory`:

```xml
<!-- Maven: trong <dependencies> của project benchmark Java 17. -->
<dependency>
    <groupId>org.apache.activemq</groupId>
    <artifactId>activemq-client</artifactId>
    <version>6.4.0</version>
</dependency>
<dependency>
    <groupId>org.apache.artemis</groupId>
    <artifactId>artemis-jakarta-client</artifactId>
    <version>2.57.0</version>
</dependency>
```

Trong ứng dụng production, **ưu tiên một provider được kiểm soát theo BOM**; hai client chỉ cùng có mặt để phục vụ lab so sánh. Nếu dependency transitives xung đột, tách thành hai module lab có **code JMS dùng chung**, mỗi module chỉ một provider. Với Classic 5.x phải chọn đúng biến thể `javax.jms`/`jakarta.jms` tương thích.

### 7.1. `JmsFactorBench.java`

```java
import jakarta.jms.BytesMessage;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.JMSProducer;
import jakarta.jms.Message;
import jakarta.jms.Queue;

import java.util.Arrays;
import java.util.Random;
import java.util.concurrent.TimeUnit;

public final class JmsFactorBench {
    private JmsFactorBench() {}

    private static String env(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing environment: " + name);
        }
        return value;
    }

    // Xác nhận đồng bộ trên cả hai delivery modes khi chạy bài lab.
    private static ConnectionFactory factory(String kind, String uri)
            throws Exception {
        if ("classic".equals(kind)) {
            org.apache.activemq.ActiveMQConnectionFactory cf;
            if (uri.startsWith("ssl://")) {
                org.apache.activemq.ActiveMQSslConnectionFactory ssl =
                    new org.apache.activemq.ActiveMQSslConnectionFactory(uri);
                ssl.setTrustStore(env("JMS_TLS_TRUSTSTORE"));
                ssl.setTrustStorePassword(env("JMS_TLS_TRUSTSTORE_PASSWORD"));
                cf = ssl;
            } else {
                cf = new org.apache.activemq.ActiveMQConnectionFactory(uri);
            }
            cf.setUseAsyncSend(false);
            cf.setAlwaysSyncSend(true);
            return cf;
        }
        if ("artemis".equals(kind)) {
            if (uri.contains("sslEnabled=true")) {
                // Chỉ áp dụng trong JVM benchmark cô lập; đây là JSSE
                // system properties có phạm vi toàn tiến trình.
                System.setProperty("javax.net.ssl.trustStore",
                    env("JMS_TLS_TRUSTSTORE"));
                System.setProperty("javax.net.ssl.trustStorePassword",
                    env("JMS_TLS_TRUSTSTORE_PASSWORD"));
                System.setProperty("javax.net.ssl.trustStoreType", "PKCS12");
            }
            return new org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory(uri);
        }
        throw new IllegalArgumentException("Use classic or artemis");
    }

    private static double p99Millis(long[] values, int used) {
        if (used == 0) return Double.NaN;
        Arrays.sort(values, 0, used);
        int index = Math.max(0, (int) Math.ceil(used * 0.99) - 1);
        return values[index] / 1_000_000.0;
    }

    private static void send(ConnectionFactory cf, String user, String pass,
                             String queueName, String runId, int count,
                             int bodyBytes, boolean persistent, int batch) {
        int sessionMode = batch > 0
            ? JMSContext.SESSION_TRANSACTED
            : JMSContext.AUTO_ACKNOWLEDGE;
        byte[] body = new byte[bodyBytes];
        new Random(42).nextBytes(body); // Cố định content, khó nén hơn 0x00.

        long[] sendCosts = new long[count];
        long[] commitCosts = new long[batch > 0
            ? (count + batch - 1) / batch : 0];
        int commits = 0;

        long setupAt = System.nanoTime();
        try (JMSContext ctx = cf.createContext(user, pass, sessionMode)) {
            Queue queue = ctx.createQueue(queueName);
            JMSProducer producer = ctx.createProducer().setDeliveryMode(
                persistent ? DeliveryMode.PERSISTENT
                           : DeliveryMode.NON_PERSISTENT);
            long setupNs = System.nanoTime() - setupAt;
            long started = System.nanoTime();

            for (int i = 0; i < count; i++) {
                BytesMessage message = ctx.createBytesMessage();
                message.writeBytes(body);
                message.setStringProperty("runId", runId);
                message.setIntProperty("seq", i + 1);
                long at = System.nanoTime();
                producer.send(queue, message);
                sendCosts[i] = System.nanoTime() - at;

                if (batch > 0 &&
                        ((i + 1) % batch == 0 || i + 1 == count)) {
                    long commitAt = System.nanoTime();
                    ctx.commit();
                    commitCosts[commits++] =
                        System.nanoTime() - commitAt;
                }
            }
            double seconds = (System.nanoTime() - started) / 1e9;
            System.out.printf(
                "SEND_RETURNED count=%d bytes=%d persistent=%s "
              + "batch=%d setupMs=%.1f msgPerSec=%.1f payloadMiBps=%.1f "
              + "sendP99ms=%.2f commitP99ms=%.2f%n",
                count, bodyBytes, persistent, batch,
                setupNs / 1e6, count / seconds,
                (count * (double) bodyBytes / 1_048_576.0) / seconds,
                p99Millis(sendCosts, count),
                p99Millis(commitCosts, commits));
        }
    }

    private static void drain(ConnectionFactory cf, String user, String pass,
                              String queueName, String runId, int count,
                              int bodyBytes, int batch) throws Exception {
        int sessionMode = batch > 0
            ? JMSContext.SESSION_TRANSACTED
            : JMSContext.AUTO_ACKNOWLEDGE;
        try (JMSContext ctx = cf.createContext(user, pass, sessionMode)) {
            Queue queue = ctx.createQueue(queueName);
            JMSConsumer consumer = ctx.createConsumer(queue);
            ctx.start();
            long firstReceiveAt = -1;
            for (int i = 0; i < count; i++) {
                Message message = consumer.receive(15_000L);
                if (!(message instanceof BytesMessage binary)) {
                    throw new IllegalStateException(
                        "Expected BytesMessage: index=" + i);
                }
                if (firstReceiveAt < 0) {
                    firstReceiveAt = System.nanoTime();
                }
                if (!runId.equals(message.getStringProperty("runId"))
                        || message.getIntProperty("seq") != i + 1
                        || binary.getBodyLength() != bodyBytes) {
                    throw new IllegalStateException(
                        "Wrong run/order/bytes at index=" + i);
                }
                if (batch > 0 &&
                        ((i + 1) % batch == 0 || i + 1 == count)) {
                    ctx.commit();
                }
            }
            double seconds =
                (System.nanoTime() - firstReceiveAt) / 1e9;
            System.out.printf("DRAIN_ACKED count=%d elapsedSec=%.3f%n",
                count, seconds);
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 8) {
            throw new IllegalArgumentException(
                "Usage: <classic|artemis> <send|drain> <queue> "
              + "<runId> <count> <bodyBytes> <P|NP> <batch>");
        }
        String kind = args[0], operation = args[1],
               queue = args[2], runId = args[3];
        if (!runId.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("Invalid runId");
        }
        int count = Integer.parseInt(args[4]);
        int bodyBytes = Integer.parseInt(args[5]);
        int batch = Integer.parseInt(args[7]);
        if (count < 1 || count > 100_000 ||
                bodyBytes < 1 || bodyBytes > 1_048_576 ||
                batch < 0 || batch > count) {
            throw new IllegalArgumentException("Out-of-range lab inputs");
        }
        if (!args[6].equals("P") && !args[6].equals("NP")) {
            throw new IllegalArgumentException("Use P or NP");
        }
        ConnectionFactory cf = factory(kind, env("JMS_BROKER_URL"));
        try {
            if ("send".equals(operation)) {
                send(cf, env("JMS_USER"), env("JMS_PASSWORD"),
                    queue, runId, count, bodyBytes, "P".equals(args[6]), batch);
            } else if ("drain".equals(operation)) {
                drain(cf, env("JMS_USER"), env("JMS_PASSWORD"),
                    queue, runId, count, bodyBytes, batch);
            } else {
                throw new IllegalArgumentException("Use send or drain");
            }
        } finally {
            if (cf instanceof org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory artemisFactory) {
                artemisFactory.close();
            }
        }
    }
}
```

### 7.2. Cách chạy an toàn trên lab

**Artemis TCP không TLS**, với broker đã tạo queue và quyền JMS phù hợp:

```text
JMS_BROKER_URL=tcp://broker.lab.example:61616?blockOnDurableSend=true&blockOnNonDurableSend=true&minLargeMessageSize=102400&compressLargeMessage=false
JMS_USER=<lab-user>
JMS_PASSWORD=<runtime-secret>

java JmsFactorBench artemis drain lab.performance.factors runA0 5000 4096 P 50
java JmsFactorBench artemis send  lab.performance.factors runA0 5000 4096 P 0
```

Hai dòng `java` trên phải chạy ở **hai terminal/tiến trình riêng**, **drain trước** rồi send. Các dòng environment là cú pháp mô tả **giá trị cần cung cấp**, không phải file script có thể paste trực tiếp vào mọi loại shell; tránh để mật khẩu xuất hiện trong shell history. Thay `broker.lab.example` bằng host thật và dùng queue lab trống.

**Classic TCP không TLS**, định nghĩa URL tương ứng:

```text
JMS_BROKER_URL=tcp://classic.lab.example:61616

java JmsFactorBench classic drain lab.performance.factors runC0 5000 4096 P 50
java JmsFactorBench classic send  lab.performance.factors runC0 5000 4096 P 0
```

**Đối chiếu TLS:**

- Với Classic, đổi URL thành `ssl://classic.lab.example:61617` và cấp `JMS_TLS_TRUSTSTORE`/`JMS_TLS_TRUSTSTORE_PASSWORD` cho `ActiveMQSslConnectionFactory`.
- Với Artemis, đổi URL sang `tcp://broker.lab.example:61617?sslEnabled=true&verifyHost=true&blockOnDurableSend=true&blockOnNonDurableSend=true&minLargeMessageSize=102400&compressLargeMessage=false` và cấp truststore PKCS12 như mã.
- Certificate phải có SAN khớp host, broker acceptor/connector đã bật TLS đúng và client **không** bật chế độ trust-all. Đo cùng run size/mode/batch sau khi connection sẵn sàng.

**Để đo transaction batch:** thay trường cuối của `send` từ `0` thành `1`, `10` và `100`; **giữ nguyên P, payload và TLS**, chạy với `runId`/queue sạch mới cho mỗi lượt. Giữ consumer cùng `batch=50` để chỉ thay producer; nếu muốn nghiên cứu **consumer transaction batch**, thực hiện một ma trận độc lập thay tham số `drain`.

### 7.3. Điều harness này đo được và chưa đo được

- `sendP99ms` phản ánh thời gian gọi API `send()`; trong transaction nó **không tính** `commit()`, vì vậy phải đọc `commitP99ms` và throughput chung cùng nhau.
- Code đo thời gian từ **sau tạo JMSContext/producer** tới lần gửi/commit cuối. `setupMs` là ước lượng giai đoạn tạo context/objects; tùy provider, một phần handshake/lazy initialization có thể xảy ra ở send đầu tiên. Cần warm-up và đo riêng setup/connect TLS handshake nếu đó là mục tiêu.
- `drain` chỉ xác minh metadata, thứ tự và ACK, **không** giả lập database/HTTP side effect; đây là throughput broker/JMS path, không phải end-to-end latency nghiệp vụ.
- `drain` kiểm tra `seq` tăng dần để phát hiện nhiễu từ test khác trong một producer/consumer **queue lab đơn giản**. Khi có competing consumers, redelivery hoặc selector, điều kiện thứ tự này không còn được đảm bảo.
- `AUTO_ACKNOWLEDGE` của consumer tại `batch=0` được provider xử lý theo hợp đồng JMS. `batch>0` gom ACK trong transaction. Đừng xem chúng tương đương khi có crash.
- Mã đặt `alwaysSyncSend=true` ở Classic và yêu cầu URL `blockOnDurableSend=true`/`blockOnNonDurableSend=true` ở Artemis để so persistence trong **mode xác nhận**, chứ không phải đo tốc độ fire-and-forget mặc định của nonpersistent.
- Chương trình **không tự khởi động broker**, provision queue, cấu hình TLS hay xuất metrics từ OS. Hãy lấy broker/disk/CPU/network telemetry bằng hệ giám sát của lab.

**Một cảnh báo đo lường:** nếu producer nhận exception ở `commit()` do mất kết nối, batch đó có thể **IN_DOUBT**. Không tự động chạy lại toàn bộ batch như thể nó chưa từng tồn tại; đối chiếu theo `runId`/`seq` và quyết định replay phù hợp.

## 8. Cách đọc kết quả: tại sao một factor có thể làm factor khác đổi nghĩa

Không có một con số throughput “đúng” cho Classic hoặc Artemis độc lập với workload. Bảng dưới cho thấy **xu hướng có thể xảy ra**, không phải số liệu đã đo:

| Điều thay đổi | Xu hướng có thể thấy | Khi nào kết luận cần thận trọng |
|---|---|---|
| Tăng size từ 1 KiB lên 64 KiB | msg/s giảm; MiB/s có thể tăng rồi chạm trần | Payload encoding, GC, TCP buffer và disk cạnh tranh |
| Vượt ngưỡng large-message Artemis | p99 tăng hoặc thay đổi đột ngột | Đây là **đổi code path**, không chỉ tăng byte |
| PERSISTENT → NON_PERSISTENT | Giảm disk sync overhead; throughput có thể tăng | Nếu send chuyển async thì thêm **thay đổi confirmation** |
| TCP → TLS | CPU tăng; connection setup chậm hơn; MiB/s có thể giảm | Nếu reconnect liên tục, đo handshake chứ không phải steady-state |
| Transaction batch 1 → 10 | Ít commit round trip; msg/s thường cải thiện | Có thêm in-flight/uncommitted và rollback theo batch |
| Transaction batch 10 → 1000 | Có thể tăng throughput rồi bão hòa | Tail latency, memory, retry batch và SLA có thể tệ hơn |
| Thêm consumer | Broker drain nhanh hơn nếu processing là nút thắt | Nếu storage/DB/nic đã bão hòa, thêm consumer làm xấu latency |

### 8.1. Một bảng kết quả minh họa (KHÔNG phải benchmark)

| Cấu hình | msg/s | payload MiB/s | send p99 | commit p99 | Ghi chú |
|---|---:|---:|---:|---:|---|
| 4 KiB, P, TCP, non-tx synchronous | 4.000 | 15,6 | 3,5 ms | — | Mốc ví dụ |
| 4 KiB, NP, TCP, non-tx synchronous | 11.000 | 43,0 | 1,4 ms | — | Không có durability tương đương |
| 4 KiB, P, TLS, non-tx synchronous | 3.500 | 13,7 | 4,0 ms | — | TLS có thêm CPU |
| 4 KiB, P, TCP, transaction batch=10 | 13.000 | 50,8 | 0,7 ms | 5,2 ms | send p99 **không gồm** commit |

Các số này **được đặt giả định để luyện cách đọc**; không dùng để đánh giá sản phẩm hay sizing. Trong batch=10, một commit p99 5,2 ms có thể vẫn khiến một số message chờ từ lâu trước commit; cần đo **p99 event-to-commit** nếu SLO yêu cầu.

### 8.2. Nút thắt có thể chuyển lớp giữa các phép đo

Giả sử baseline persistent bị giới hạn bởi độ trễ fsync. Chuyển sang batch=100 giảm số fsync/roundtrip nên CPU mã hóa TLS hoặc băng thông NIC có thể trở thành nút thắt mới. Bật TLS sau đó làm throughput giảm đáng kể **không có nghĩa TLS là nút thắt lớn trong baseline batch=1**.

Vì thế nên đo cả **main effects** (mỗi lần chỉ thay một factor) lẫn một số **interaction cases**, ví dụ:

- 1 KiB và 256 KiB, cả TCP lẫn TLS;
- persistent và nonpersistent, cả non-tx sync lẫn transacted batch=10;
- batch=1 và batch=100, cả SSD nhanh lẫn storage network/CSI đang dùng thực tế.

Không suy rằng phần trăm tăng/giảm của bốn factor có thể **cộng** lại để dự đoán production. Chúng thường tương tác và có điểm bão hòa.

## 9. Vấn đề chẩn đoán thường gặp

| Triệu chứng | Điều cần xác minh | Cách xử lý đúng |
|---|---|---|
| Nonpersistent nhanh gấp nhiều lần | Nonpersistent có đang fire-and-forget trong khi P đợi ACK? | Bật mode confirmation tương đương để so đúng factor, ghi riêng tốc độ mặc định |
| Payload 128 KiB p99 tăng vọt trên Artemis | `minLargeMessageSize` và large-message directory | Giữ ngưỡng cố định; đo I/O/fragmentation; không quy mọi lỗi về Java GC |
| TLS “chậm 10×” khi gửi mỗi message | Có đang mở connection mới mỗi send? | Reuse ConnectionFactory/Session/Producer, đo handshake riêng |
| TLS kết nối thất bại | SAN/CA/truststore, enabled protocols, client/server acceptor | Cấu hình certificate đúng; không tắt verifyHost hoặc trustAll |
| Transaction tăng throughput nhưng mất dữ liệu khi crash | Sync flags tắt hoặc volume ephemeral? | Khôi phục sync/durability, test failover và commit semantics |
| Batch lớn làm consumer thấy message muộn | Message chưa visible trước transaction commit | Chọn batch theo latency SLO, không chỉ msg/s |
| Producer đứng vì address đầy | Broker flow control/paging, consumer không theo kịp | Xem queue depth, store/memory usage và khả năng drain |
| `send()` đã trả nhưng queue không có message | Sai destination, TTL, selector, consumer khác, async send, transaction rollback | Dùng runId/seq, đọc log/metrics, không suy mất dữ liệu chỉ từ queue trống |
| Throughput tăng sau lượt thử thứ hai | JIT, journal preallocation, page cache/TLS session warm-up | Warm-up, tráo thứ tự test, lấy median nhiều lần |
| p99 thấp nhưng backlog tăng | Publish nhanh hơn drain; đo chỉ producer | Ghi cùng consumer rate và backlog theo thời gian |

### Các chỉ số nên thu thập cùng một thời điểm

**Client:** msg/s, payload MiB/s, p50/p95/p99 `send` và `commit`, CPU/GC/allocation, số connection/session và lỗi timeout.

**Broker:** `QueueSize`/`messageCount`, enqueue/dequeue rate, in-flight/delivering, memory/store/paging, journal write latency, disk queue depth, network bytes, connections và số transaction.

**Sản phẩm/nghiệp vụ:** độ trễ từ event được tạo đến side effect thành công, duplicate processing, timeout retry, message expired/DLQ và thời gian khôi phục sau fault.

Không lấy `DispatchCount` làm business success count: một message có thể dispatch lại sau rollback. Không suy từ `msg/s` mà không có `MiB/s` khi so size khác nhau. Với HA, cần đo throughput **trong và sau failover** riêng thay vì trộn vào steady-state.

## 10. Checklist trước khi đưa kết luận hiệu năng

- [ ] Đã ghi rõ broker/version, provider/JMS API, JDK, CPU/RAM quota, network RTT, storage/volume, TLS cipher và journal type.
- [ ] Cùng queue/protocol, kích thước body tính theo **byte thật**, cùng headers và codec; ghi rõ large-message threshold.
- [ ] `PERSISTENT` và `NON_PERSISTENT` được so với **chính sách xác nhận gửi tương đương**, hoặc ghi rõ lý do khác.
- [ ] Không tắt sync/persistence/security của production chỉ để tăng throughput; nếu đổi độ bền phải báo thành một scenario khác.
- [ ] TLS thử trên connection reuse; truststore, SAN và hostname verification hợp lệ.
- [ ] So transaction `batch=1,10,100` trong cùng session mode; đo cả send lẫn commit latency.
- [ ] Consumer drain theo kịp producer, không xảy ra paging bất ngờ; nếu xảy ra thì tách kết quả thành bài thử pressure/capacity.
- [ ] Có warm-up, ≥3 lượt đo, median, p95/p99 và sai số; không lấy số lớn nhất làm kết quả.
- [ ] Đã so `runId`/`seq`, số ACK và ledger để loại trừ message thất lạc do test harness; timeout được đánh dấu `IN_DOUBT`.
- [ ] Đã kiểm tra p99 end-to-end và khả năng phục hồi/durability, không tối ưu msg/s bằng mọi giá.

**Kết luận:** kích thước message đổi tỷ trọng CPU/băng thông/disk và có thể chuyển sang large-message path; persistence thêm chi phí đồng bộ để đổi lấy khả năng khôi phục; TLS thêm chi phí xác thực/mã hóa nhưng handshake thường được phân bổ trên connection tái sử dụng; transaction batch phân bổ chi phí commit trên nhiều message nhưng tăng lượng công việc chưa commit và tail latency. **Benchmark có ý nghĩa chỉ khi bốn factor được cô lập, confirmation/durability tương đương và cả broker lẫn consumer đều được quan sát.**

## Tài liệu chính thức

1. [Apache Artemis 2.57.0 — Performance Tuning](https://artemis.apache.org/components/artemis/documentation/latest/perf-tuning.html): batching, persistence, JMS overhead, transport và anti-pattern tạo connection mỗi lần gửi.
2. [Apache Artemis 2.57.0 — Guarantees of Sends and Commits](https://artemis.apache.org/components/artemis/documentation/latest/send-guarantees.html): `blockOnDurableSend`, `blockOnNonDurableSend` và durability tại transaction commit.
3. [Apache Artemis 2.57.0 — Large Messages](https://artemis.apache.org/components/artemis/documentation/latest/large-messages.html): `minLargeMessageSize`, fragment và compression.
4. [Apache Artemis 2.57.0 — Configuring the Transport](https://artemis.apache.org/components/artemis/documentation/latest/configuring-transports.html): Netty TLS, `sslEnabled`, truststore, `verifyHost` và cipher selection.
5. [Apache Artemis 2.57.0 — Persistence](https://artemis.apache.org/components/artemis/documentation/latest/persistence.html): journal, sync flags và persistence store.
6. [ActiveMQ Classic — Performance Tuning](https://activemq.apache.org/components/classic/documentation/performance-tuning): persistent/async send, prefetch và xác nhận.
7. [ActiveMQ Classic — Connection Configuration URI](https://activemq.apache.org/components/classic/documentation/connection-configuration-uri): `useAsyncSend` và `alwaysSyncSend`.
8. [ActiveMQ Classic — SSL Transport Reference](https://activemq.apache.org/components/classic/documentation/ssl-transport-reference): `ActiveMQSslConnectionFactory`, TLS connector và hostname verification.
