# Ảnh hưởng của selector tới phân phối tải và message tồn trong JMS

> **Module:** Spring Framework – JMS  
> **Chủ đề cha:** Lọc thông điệp  
> **Trọng tâm:** Message selector thay đổi tập consumer đủ điều kiện nhận message, do đó tác động đến phân phối tải, backlog và các message không có consumer phù hợp.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả đúng message selector trong Jakarta Messaging: điều kiện SQL92-subset đánh giá **JMS headers/properties**, không đọc trực tiếp body.
2. Giải thích trên **Queue**: message khớp selector của consumer nào thì consumer đó có thể nhận; message không khớp có thể được consumer khác nhận hoặc **tiếp tục nằm trong queue**, thay vì biến mất.
3. Giải thích trên **Topic**: selector giới hạn message được **đưa vào từng subscription**, khác hoàn toàn việc để lại message không khớp trong một queue dùng chung.
4. Phân tích tải giữa nhiều consumer khi selector **loại trừ nhau**, **chồng lấn**, **bao phủ không đủ** hoặc một nhóm consumer ngừng hoạt động.
5. Nhận biết message tồn vì thiếu JMS property, property sai kiểu/case, điều kiện đánh giá ra `UNKNOWN`, không có matching consumer, consumer bị tắc, hoặc cấu hình durable subscription chưa đúng.
6. Dùng `Session.createConsumer(..., selector)`, `JMSContext.createConsumer(..., selector)` và `@JmsListener(selector = "...")` trong ứng dụng Spring JMS.
7. Đo queue depth, pending theo phân loại, message age, consumer counts, throughput, redelivery và expiration để phân biệt **lọc sai** với **worker thiếu công suất**.
8. Chọn thiết kế giữa một queue kèm selectors, nhiều queue riêng theo nhóm, và topic với subscriptions phù hợp, kể cả khi cần fan-out.

## 1. Message selector thực sự làm gì?

Một **message selector** là biểu thức điều kiện được đăng ký **khi tạo JMS consumer/subscription**. Jakarta Messaging cho phép provider thay ứng dụng kiểm tra một tập JMS headers và message properties, chỉ giao message **khớp điều kiện** cho consumer/subscription đó.

Ví dụ message có các properties:

```text
JMSDestination = Queue:dispatch.jobs
JMSPriority    = 4
region         = "NORTH"     (String property)
tier           = 2           (int property)
kind           = "INVOICE"   (String property)
```

Consumer đăng ký:

```sql
region = 'NORTH' AND tier >= 2
```

Message này đủ điều kiện nhận vì hai nhánh đều đúng. Consumer có selector `region = 'SOUTH'` **không đủ điều kiện** nhận message đó.

Một selector **không phải**:

- Lệnh để **producer** chỉ gửi message tới một consumer có tên cụ thể.
- Predicate Java chạy sau khi consumer đã nhận message rồi mới `if`/`else` trong handler.
- Quy tắc tự chuyển message không khớp sang **DLQ**.
- Cơ chế bảo đảm phân phối đều theo round-robin.
- Cách tìm kiếm JSON field nằm trong `TextMessage.getText()`.
- Điều kiện tự động áp dụng cho mọi consumer khác của cùng destination.

Nó chỉ định **tập message consumer muốn nhận**. Hệ quả trên Queue và Topic **khác nhau**, đây chính là tâm điểm của bài.

### 1.1. Ranh giới kiểm tra: headers/properties, không phải body

```text
Message
  |-- JMS headers (một tập tên cho phép dùng trong selector)
  |-- application properties: region, kind, tier, tenantId...
  |-- body: JSON / binary / TextMessage / MapMessage / ...
          X selector chuẩn không đọc trực tiếp các field trong body
```

Nếu body có `{"region":"NORTH"}` nhưng **không có JMS property** tên `region`, selector `region = 'NORTH'` **không khớp**. Property là metadata độc lập với nội dung body. Producer cần sao chép những trường dùng để routing thành **JMS properties được khai báo rõ**.

Không phải header JMS nào cũng có thể dùng trong selector. Các standard header field được phép tham chiếu theo Jakarta Messaging gồm `JMSDeliveryMode`, `JMSPriority`, `JMSMessageID`, `JMSTimestamp`, `JMSCorrelationID` và `JMSType`. Ví dụ `JMSPriority >= 7` hợp lệ. Đừng mặc nhiên lấy `JMSDestination`, `JMSReplyTo`, `JMSExpiration` hay nội dung body làm trường filter portable.

### 1.2. Cách hoạt động khác nhau theo Destination

```text
                 Producer
                    |
         +----------+------------+
         |                       |
         v                       v
      QUEUE                      TOPIC
  dispatch.jobs               orders.events
         |                       |
         |                       +--> Subscription Audit
         |                       |       selector: kind='INVOICE'
         |                       |
         +--> Consumer NORTH     +--> Subscription Analytics
         |      selector:NORTH           selector: amount>=1000
         |
         +--> Consumer SOUTH
                selector:SOUTH

QUEUE: một message được giao cho một matching consumer.
       Không có match -> message có thể chờ trong queue.

TOPIC: mỗi subscription độc lập tự xét selector.
       Không match subscription -> không thêm bản sao vào subscription đó.
```

Đừng dùng hình thức “hai consumer đều có selector” để suy luận rằng hai consumer queue đều được nhận mọi message phù hợp. **Queue là competing consumers; Topic có các subscription riêng**. <u>Selector không làm queue thành topic.</u>

## 2. Queue: selector làm thay đổi người có thể nhận message

Theo đặc tả Jakarta Messaging về point-to-point, một queue có thể có nhiều consumer. Một message được giao tới **chỉ một consumer ở mỗi lần delivery**, và nếu consumer có selector thì message phải khớp selector đó. Message không được consumer này chọn **vẫn nằm trong queue hoặc được consumer khác nhận**.

### 2.1. Hai worker theo vùng, điều kiện loại trừ nhau

Giả sử cùng queue `dispatch.jobs`:

- `WorkerNorth`: `region = 'NORTH'`
- `WorkerSouth`: `region = 'SOUTH'`

Producer gửi:

| Message | JMS property `region` | Consumer đủ điều kiện |
| --- | --- | --- |
| `M-1` | `NORTH` | North |
| `M-2` | `SOUTH` | South |
| `M-3` | `NORTH` | North |
| `M-4` | `WEST` | **Không ai** |
| `M-5` | **Thiếu property** | **Không ai** |

```text
                        Queue dispatch.jobs
                    M-1  M-2  M-3  M-4  M-5
                       |    |    |    X    X
                       v    v    v    |    |
                    North South North +----+--> vẫn chờ
```

Với giả định broker đã nhận thành công message, chưa hết hạn, chưa bị xóa bởi policy và chỉ có hai consumer đó, `M-4`/`M-5` **không có consumer đủ điều kiện**. Chúng không tự biến thành DLQ chỉ vì không khớp selector; queue có thể tích lũy chúng, chờ consumer mới có selector phù hợp (hoặc consumer không dùng selector), hoặc chờ policy broker khác.

**Điểm then chốt:** phần backlog này có thể tăng **mặc dù North và South đang chạy bình thường và xử lý rất nhanh**.

### 2.2. Nhiều worker cùng một selector vẫn cạnh tranh tải

Giả sử:

- `North A`, `North B` cùng selector `region = 'NORTH'`.
- `South C` selector `region = 'SOUTH'`.

Message `region=NORTH` đủ điều kiện cho cả A và B, nhưng mỗi lần giao chỉ **một** người trong hai nhận. Nếu có redelivery sau rollback, provider có thể giao lại, do đó không suy ra “exactly once business processing”.

```text
      NORTH messages
         /     \
        v       v
   North A    North B    (competing within NORTH)
       \        /
     cùng một queue và cùng loại công việc

      SOUTH messages
          |
          v
       South C
```

Cách phân phối giữa A và B **không được JMS bắt buộc là 50/50**. Broker có thể xét khả năng nhận, prefetch, active consumers, transaction, priority, message grouping, connection speed và chính sách phân phối riêng. “Hai worker” là tăng **khả năng xử lý**, không phải cam kết round-robin.

### 2.3. Selector chồng lấn: không phải fan-out

Giả sử consumer A dùng:

```sql
region = 'NORTH'
```

Consumer B dùng:

```sql
tier >= 3
```

Một message `region=NORTH, tier=3` **khớp cả A và B**. Trên **Queue**, provider có thể giao message đó cho **A hoặc B**, nhưng không tạo hai bản sao chỉ vì hai selector đều đúng. Kết quả là:

- A có thể giành message ưu tiên mà B cũng muốn.
- B có thể xử lý message vùng NORTH, dù ý định B là một luồng công việc khác.
- Tải thực tế theo từng listener có thể khó dự đoán.
- Nếu A và B thực hiện **hai nghiệp vụ độc lập**, việc đặt họ làm hai consumer cùng queue là sai kiến trúc: phải dùng Topic với hai subscription hoặc fan-out rõ ràng.

**Không coi selector là quy tắc ưu tiên**: selector chỉ nói “được phép nhận” chứ không xác lập thứ tự chọn consumer khi nhiều người cùng đủ điều kiện.

### 2.4. Selector không bao phủ: message tồn

Nếu tất cả consumer đều lọc chỉ `NORTH`/`SOUTH`, còn producer vẫn gửi `WEST` hoặc thiếu `region`, backlog chứa message không ai xử lý.

Hậu quả:

1. Queue depth tăng, ngay cả khi consumer status vẫn “healthy”.
2. Pending count có thể ở mức cao nhưng throughput tiếp tục tăng đối với nhóm hợp lệ.
3. Dữ liệu tồn có thể chiếm quota/disk/memory của broker.
4. Tùy implementation, việc quét/duyệt message và tìm match có thể làm tăng chi phí, latency hoặc gây head-of-line-like effects; **không hứa mọi broker luôn bị chặn bởi message không khớp ở đầu queue**.
5. Nếu các message này chưa expired, chúng vẫn không có consumer phù hợp. Dù tăng thêm North workers, chúng cũng không giúp xử lý `WEST`.
6. Khi thêm đúng `WestWorker` hoặc consumer được phép đọc mọi message, backlog có thể giảm. Tuy nhiên, một consumer không có selector có thể **cạnh tranh lấy cả message NORTH/SOUTH**, nên không dùng nó như “fallback chỉ nhận unmatched” nếu không có routing policy riêng.

### 2.5. Selector không tự tạo nhóm “không khớp”

Nghe có vẻ hợp lý: thêm consumer với selector `region <> 'NORTH' AND region <> 'SOUTH'` để bắt tất cả message lỗi.

Nhưng có bẫy:

- Khi property `region` **không tồn tại**, phép so sánh với giá trị `NULL` đánh giá ra `UNKNOWN`, nên `region <> 'NORTH'` **không trả TRUE**.
- Với message có property sai kiểu hoặc nội dung không hợp lệ, một số so sánh cũng không trả TRUE như lập trình viên kỳ vọng.
- Biểu thức fallback cần xét thiếu property rõ ràng, ví dụ `region IS NULL`, và vẫn phải kiểm tra loại dữ liệu/chính sách broker.
- Nếu consumer không filter được tất cả dạng lỗi, vẫn có message tồn.

An toàn hơn: **validate routing metadata trước khi publish**, phân luồng invalid vào một queue riêng, và giữ một contract JMS properties được kiểm thử. Không cố giải mọi loại invalid message bằng một selector phức tạp.

## 3. Topic: selector lọc message được thêm vào từng subscription

Topic dùng mô hình publish/subscribe. Producer publish một message; mỗi **subscription độc lập** được nhận bản sao những message phù hợp selector của chính subscription ấy, tính từ khi subscription tồn tại theo lifecycle của nó.

### 3.1. Hai subscription độc lập, selector khác nhau

Topic `orders.events` có:

- Subscription `Audit`: `kind = 'INVOICE'`.
- Subscription `Metrics`: `amount >= 1_000` — lưu ý **JMS selector không hỗ trợ dấu gạch dưới trong numeric literal kiểu Java**; selector thực tế phải viết `amount >= 1000`.

Giả sử có ba message:

| Event | `kind` | `amount` int | Audit | Metrics |
| --- | --- | ---: | --- | --- |
| E1 | INVOICE | 1500 | Có bản sao | Có bản sao |
| E2 | INVOICE | 50 | Có bản sao | Không |
| E3 | PAYMENT | 2000 | Không | Có bản sao |

`E1` khớp **hai subscription**, do vậy mỗi subscription độc lập được thêm một bản sao. Ack/commit ở Audit không thay thế ack/commit ở Metrics. `E2` không khớp Metrics nên **không được thêm vào subscription Metrics**; nó không “nằm chờ Metrics đổi selector” như một message trên queue dùng chung.

### 3.2. Non-durable và durable ảnh hưởng message tồn khác nhau

**Non-durable subscription**:

- Nhận message phù hợp trong thời gian subscription tồn tại.
- Khi không còn subscriber, message tương lai **không được giữ để subscriber mới bất kỳ nhận hồi tố** theo JMS.
- Nếu chưa tạo subscription trước lúc producer publish, không thể đòi lịch sử event.

**Durable subscription**:

- Có identity (subscription name và các thuộc tính danh tính/client ID phù hợp).
- Provider duy trì subscription khi consumer tắt; message **khớp selector** được thêm vào backlog của subscription để xử lý sau, theo delivery mode, expiration và chính sách broker.
- Message **không khớp** selector **không được thêm vào backlog subscription đó**, nên subscriber đổi ý sau này không tự nhận lại.
- Có thể tạo nhiều **subscription độc lập** cho các nghiệp vụ khác nhau, mỗi subscription có backlog và ack riêng.

**Shared subscription**:

- Nhiều consumer cùng một shared subscription chia tải: một bản message của subscription được giao tới **một consumer** trong nhóm.
- Shared subscription không đồng nghĩa nhiều subscription độc lập; nếu cần hai ứng dụng đều thấy một event, cần hai subscription riêng.

### 3.3. Thay selector trên durable subscription là thay hợp đồng lưu giữ

Trong Jakarta Messaging, một durable subscription có identity, topic và selector gắn với state của nó. Với unshared durable subscription, tạo lại theo cùng identity nhưng **selector khác** (khi không có consumer active) tương đương xóa subscription cũ rồi tạo subscription mới. Những message pending cũ có nguy cơ mất khỏi subscription theo hợp đồng này.

**Không âm thầm sửa selector durable ở production** như thay một điều kiện SQL truy vấn database rồi mong backlog cũ được giữ nguyên. Khi thay đổi yêu cầu nhận event, phải lập kế hoạch migration, đổi subscription name có chủ đích, xử lý backlog, đối chiếu duplicate/missing events và kiểm thử broker cụ thể. Với shared subscription, quy tắc về việc tạo lại và thay đổi selector có những ràng buộc riêng; không giả định thay selector động được trên consumer đang hoạt động.

### 3.4. So sánh cùng điều kiện trên Queue và Topic

| Câu hỏi | Queue có consumer selector | Topic có subscription selector |
| --- | --- | --- |
| Message khớp hai consumer/subscription? | **Một consumer** được giao trong mỗi lần delivery | **Mỗi subscription độc lập** có thể có bản sao |
| Message không khớp consumer A? | Có thể được consumer B nhận hoặc **còn trong queue** | Không được thêm vào **subscription A** |
| A không online? | Message queue có thể vẫn chờ, theo policy | Non-durable không bảo đảm backlog; durable có thể tích backlog |
| Tăng số consumer cùng selector? | Có thể tăng throughput cho nhóm matched | Shared sub chia tải; sub độc lập tạo thêm bản sao |
| Thay selector? | Consumer mới có thể nhận message queue pending phù hợp | Không tạo lại lịch sử event đã bị loại khỏi subscription |
| Backlog quan sát ở đâu? | Pending message của queue; có thể nhiều loại nằm chung | Backlog **theo subscription**; không chỉ xem topic publish count |
| Khi không có match? | Pending/expiration/quota tùy queue/broker | Không có bản sao cho subscription đó |

**Bài học:** selector tác động đến **phân phối tải** trên Queue, nhưng với Topic còn quyết định **phạm vi bản sao/retention theo subscription**. Đây không phải một kiểu filtering “sau khi message đã về handler” chung cho mọi destination.

## 4. Các quy tắc cú pháp làm message bị “lọc oan”

JMS selector dùng một **tập con SQL92**, không phải SQL truy vấn database đầy đủ và không phải biểu thức JavaScript/SpEL.

### 4.1. Các biểu thức hợp lệ thường dùng

```sql
region = 'NORTH'
kind IN ('INVOICE', 'PAYMENT')
tier >= 2 AND enabled = TRUE
JMSPriority >= 7
eventType LIKE 'Order%'
region IS NULL
region IS NOT NULL
tier BETWEEN 2 AND 4
(region = 'NORTH' OR region = 'SOUTH') AND tier >= 2
```

Đây là các ví dụ **cú pháp selector**, không phải lệnh SQL gửi đến RDBMS. Property `region`/`tier`/`kind` phải thực sự tồn tại và có kiểu phù hợp trên message.

Các ký hiệu quan trọng:

- String literal dùng **single quote** `'NORTH'`, không dùng double quote như chuỗi Java.
- Tên property/identifier phân biệt chữ hoa/chữ thường: `region` khác `Region`.
- Giá trị String cũng phải so khớp chính xác theo contract: `'NORTH'` khác `'north'`.
- Boolean literal là `TRUE`/`FALSE`, **không phải** String `'true'`.
- Operator phổ biến: `=`, `<>`, `>`, `>=`, `<`, `<=`, `AND`, `OR`, `NOT`, `IN`, `BETWEEN`, `LIKE`, `IS NULL`.
- Dùng dấu ngoặc để làm rõ ưu tiên `AND`/`OR`, nhất là khi phân nhóm nghiệp vụ.
- Java numeric literal có underscore như `1_000` không dùng nguyên trong selector; viết `1000`.

### 4.2. Kiểu property phải được set đúng

```java
message.setIntProperty("tier", 3);
message.setBooleanProperty("enabled", true);
message.setStringProperty("region", "NORTH");
```

Với ba lời gọi này:

```sql
tier >= 2 AND enabled = TRUE AND region = 'NORTH'
```

có thể trả TRUE.

Nhưng nếu producer viết:

```java
message.setStringProperty("tier", "3");
```

thì selector `tier >= 2` **không thực hiện số hóa String tự động theo ý nghĩ Java**. Việc so sánh không cùng kiểu có thể không khớp; JMS selector không phải phép ép String thành int tổng quát. Cách sửa đúng là thống nhất **JMS property schema** và setter, không chỉ chuyển giá trị JSON trong body.

### 4.3. NULL và ba giá trị logic TRUE/FALSE/UNKNOWN

SQL92 selector sử dụng **three-valued logic**:

- Kết quả `TRUE` → message **khớp**.
- Kết quả `FALSE` → message **không khớp**.
- Kết quả `UNKNOWN` → message **không khớp**.

Nếu property `region` vắng mặt:

| Selector | Kết quả | Message được giao cho consumer có selector này? |
| --- | --- | --- |
| `region = 'NORTH'` | UNKNOWN | Không |
| `region <> 'NORTH'` | UNKNOWN | Không |
| `NOT (region = 'NORTH')` | UNKNOWN | Không |
| `region IS NULL` | TRUE | Có |
| `region IS NOT NULL` | FALSE | Không |
| `region = 'NORTH' OR region IS NULL` | TRUE | Có |
| `region = 'NORTH' AND tier >= 2` | Có thể FALSE/UNKNOWN | Chỉ khi toàn biểu thức TRUE |

**Quan trọng:** `NOT UNKNOWN` vẫn là `UNKNOWN`, không trở thành TRUE. Đây là lý do các selector “tất cả trừ NORTH” thường **không bắt được message thiếu property**.

Ví dụ với property `region` không tồn tại, selector fallback được thiết kế rõ có thể là:

```sql
region IS NULL OR region NOT IN ('NORTH', 'SOUTH')
```

Nó bắt được missing và một số giá trị String khác, **nhưng không phải giải pháp chung** cho dữ liệu sai kiểu hoặc provider-specific behavior. Nếu route metadata không đáng tin, nên xác thực và tách luồng invalid message từ producer hoặc qua một service phân loại riêng có policy rõ ràng.

### 4.4. JMS headers được phép dùng và các bẫy

```sql
JMSPriority >= 7
JMSDeliveryMode = 'PERSISTENT'
JMSType = 'OrderCreated'
```

- `JMSPriority` là số do provider gán theo QoS gửi; không đồng nghĩa custom property `priority`.
- `JMSDeliveryMode` được biểu diễn **dưới dạng chuỗi** `'PERSISTENT'` hoặc `'NON_PERSISTENT'` khi dùng trong selector.
- `JMSType` là header đặc tả cho loại message, **không có nghĩa converter JSON tự gán nó**.
- Chỉ subset JMS standard headers được tham chiếu trực tiếp; không suy rộng tất cả getters `Message` thành selector identifiers.
- Với property `JMSX...`, xem support và semantics theo JMS/provider; không tự đặt property trong namespace dành riêng mà chưa đọc hợp đồng.

### 4.5. Thay selector không xử lý message cũ theo một nghĩa chung

Trên **Queue**, nếu một consumer mới có selector phù hợp được tạo, các message **đang pending** và chưa expired có thể trở nên eligible để delivery; không có nghĩa broker tự viết lại message.

Trên **Topic**, một subscription **không thể tự lấy lại message không bao giờ được thêm vào nó**. Thay selector không quay ngược thời gian tạo bản sao. Với durable subscription còn có rủi ro recreation và mất state cũ.

## 5. Tính tải thật: tổng consumer chưa nói lên công suất

Để hiểu vì sao tăng số worker không giảm queue backlog, hãy xét **tốc độ theo tập message** chứ không chỉ tổng số threads.

Giả sử trong mỗi giờ queue `dispatch.jobs` nhận:

- `650` message có `region=NORTH`.
- `250` message có `region=SOUTH`.
- `100` message có `region=WEST`.

Consumer capacity giả định:

- Nhóm North có thể xử lý tối đa `500` message/giờ.
- Nhóm South có thể xử lý tối đa `400` message/giờ.
- Không có consumer nào khớp `WEST`.

Giả định đơn giản: mọi message được broker chấp nhận, không expire, không có policy loại bỏ, không có redelivery/transaction làm tăng việc và không có consumer ngoài các nhóm đã nêu.

| Nhóm | Đến/giờ | Năng lực xử lý/giờ | Backlog tăng/giờ |
| --- | ---: | ---: | ---: |
| North | 650 | 500 | **150** |
| South | 250 | 400 | **0** (còn capacity rảnh) |
| West (không matching consumer) | 100 | 0 | **100** |
| Tổng | 1.000 | Tối đa 900, nhưng chỉ dùng được 750 | **250** |

Ở đây **South dư 150 message/giờ năng lực** nhưng không thể lấy message North/West vì selector không cho phép. Tổng số consumer khỏe mạnh, song queue depth vẫn tăng **250 message/giờ**. Nếu điều kiện không đổi hai giờ, backlog tăng khoảng **500 message** so với mốc đầu, bỏ qua các yếu tố đã giả định.

Một metric `consumerCount=10` không cho biết **10 consumer ấy nhận loại message nào**. Cần nhìn:

- Rate vào theo property `region`.
- Rate xử lý thành công theo selector/consumer group.
- Age của oldest eligible message và oldest unmatched message.
- Pending counts, memory/disk quota và dropped/expired/dead-letter theo chính sách.
- Số instance đang connected **và** đủ điều kiện xử lý nhóm đang tồn.

### 5.1. Mô hình đơn giản

Với mỗi phân đoạn `g`:

```text
arrivalRate[g]       = số message thuộc nhóm g đến/giây
effectiveCapacity[g] = tổng throughput thực sự của consumer đủ điều kiện cho g
backlogGrowth[g]     ≈ max(0, arrivalRate[g] - effectiveCapacity[g])
```

Đây là **mô hình xấp xỉ**, không phải công thức bảo đảm của broker. Nếu selectors chồng lấn, capacity các nhóm **không độc lập**, nên không thể cộng capacity mỗi nhóm như thể worker được cấp riêng. Nếu có retry, redelivery, prefetch, TTL, priority hay traffic dao động, số thực tế khác.

### 5.2. Chồng lấn làm khó hoạch định capacity

Ví dụ:

- Nhóm A: `region = 'NORTH'`, capacity 100/s.
- Nhóm B: `tier >= 3`, capacity 100/s.
- 60% message NORTH đồng thời `tier >= 3`.

Hai nhóm dùng **chung một queue**. Broker có thể giao những message overlap cho A hoặc B; vì vậy không có phép chia lưu lượng mặc định “mọi NORTH sang A, mọi VIP sang B” và không có cam kết cả hai business function được thực hiện. Nếu muốn hai việc độc lập xảy ra, cần tạo **hai subscription Topic** hoặc một bước routing rõ để nhân bản công việc.

### 5.3. Ineligible backlog không phải lúc nào cũng chặn mọi eligible message

Không nên dùng câu “message không khớp ở đầu queue luôn chặn cả queue” như luật của JMS. Jakarta Messaging **không bắt** tất cả provider triển khai một thuật toán scan, prefetch hay strict FIFO giống nhau. Một provider có thể tìm được message eligible sau các message unmatched; provider khác có thể gặp overhead hoặc cơ chế ưu tiên làm latency tăng.

Hệ quả thực tế: hãy đo **eligible message latency**, pending và broker implementation, không suy ra throughput chỉ từ vị trí một message trong queue.

## 6. Message tồn khác gì retry, DLQ, expiration?

Một message nằm trong queue lâu có thể vì nhiều lý do, không phải luôn do selector.

| Hiện tượng | Selector liên quan thế nào? | Cách phân biệt |
| --- | --- | --- |
| Không consumer nào match | **Nguyên nhân trực tiếp** tạo pending | Property distribution, active selector, test tạo matching consumer |
| Có matching consumer nhưng worker chậm | Selector tạo phân đoạn capacity; backlog tăng do tốc độ | Arrival vs completion rate theo nhóm |
| Consumer bị stop/disconnected | Không có active consumer đủ điều kiện | Connection/container health, listener count |
| Selector property thiếu/sai kiểu | Điều kiện FALSE/UNKNOWN | Inspect JMS properties, schema và selector expression |
| Transaction chưa commit/ack | Message có thể pending/in-flight hoặc redeliver | Transaction logs, delivery count, rollback |
| Message expire | TTL có thể loại message trước khi matching consumer nhận | `JMSExpiration`, expired counters, broker expiry policy |
| Poison message gây rollback | Retry/redelivery và DLQ theo policy | `JMSRedelivered`, retry count, DLQ |
| Prefetch giữ message ở consumer | Message có thể không ở vị trí “ready” như monitor hiển thị | Provider pending/in-flight/prefetch metrics |
| Topic durable consumer offline | Matched messages có thể tích trong **subscription backlog** | Durable subscription pending, selector identity |
| Topic selector loại message | Message không được thêm vào subscription đó | Publish count vs per-subscription accepted/matched |

**Selector không đồng nghĩa DLQ router.** Một message không khớp trên queue **không phải** message đã “failed delivery” do handler throw. DLQ thường gắn với chính sách redelivery/expiration/provider-specific routing; việc broker có “unroutable message handling” riêng không phải bảo đảm chung của JMS selector.

**Expiration không xử lý business invalid routing một cách an toàn:** Message bị expire có thể làm mất công việc quan trọng. Nếu yêu cầu “mọi đơn hàng phải xử lý”, đừng lấy TTL ngắn làm phương án xử lý nhóm không có consumer.

### 6.1. Không có matching consumer không tạo exception ở producer

Producer gửi thành công vào queue không bảo đảm hiện tại có consumer match. `JmsTemplate.send`/`convertAndSend` thường chỉ cho biết send đạt yêu cầu của API/provider; nó **không đợi một matching consumer xử lý**. Vì vậy log `"sent"` vẫn có thể xuất hiện khi queue ngày càng tồn `WEST` hoặc message không có property.

### 6.2. Vì sao không sửa bằng consumer không selector?

Nếu thêm một consumer “fallback” không selector trên **cùng queue**, consumer này đủ điều kiện cho **mọi message**, kể cả NORTH/SOUTH. Nó có thể lấy việc đúng nhóm và làm sai nghiệp vụ hoặc làm phân phối tải lệch.

Tốt hơn:

- Sửa producer để chỉ gửi route hợp lệ.
- Tạo queue riêng `dispatch.invalid` theo một bước validation có chủ đích.
- Dùng explicit destination routing: nhiều queue theo region hoặc một router application.
- Nếu cần kiểm kê message tồn, dùng admin management/QueueBrowser đọc **không tiêu thụ** thay vì một unfiltered worker vô tình ack message.

## 7. Java JMS thuần: tạo consumer có selector

### 7.1. Classic API

Giả sử đã có `jakarta.jms.ConnectionFactory` do provider cung cấp, broker/queue `dispatch.jobs` tồn tại:

```java
import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.Message;
import jakarta.jms.MessageConsumer;
import jakarta.jms.Queue;
import jakarta.jms.Session;

public final class SelectorQueueReceiver {

    private final ConnectionFactory connectionFactory;

    public SelectorQueueReceiver(ConnectionFactory connectionFactory) {
        this.connectionFactory = connectionFactory;
    }

    public void receiveNorthOnce() throws Exception {
        try (Connection connection = connectionFactory.createConnection()) {
            try (Session session =
                         connection.createSession(false, Session.AUTO_ACKNOWLEDGE)) {

                Queue queue = session.createQueue("dispatch.jobs");
                try (MessageConsumer consumer =
                             session.createConsumer(
                                     queue, "region = 'NORTH'")) {

                    connection.start();
                    Message message = consumer.receive(3_000L);

                    if (message == null) {
                        System.out.println("No NORTH message within timeout");
                    } else {
                        System.out.println(
                                "Received region=" +
                                message.getStringProperty("region"));
                    }
                }
            }
        }
    }
}
```

Đây là **class tích hợp JMS cần provider + Jakarta Messaging API**, không chạy bằng `javac` chỉ với JDK. `receive(3_000L)` chờ tối đa khoảng 3 giây rồi trả null nếu không có message eligible; **không chứng minh queue hoàn toàn rỗng**. Queue có thể còn hàng trăm message `WEST` hoặc thiếu `region`.

`Session.createConsumer(queue, selector)` yêu cầu provider tạo consumer với filter. Nếu selector sai cú pháp, provider có thể ném `InvalidSelectorException` (checked `JMSException`). Đừng coi invalid selector là “chờ mãi không có message” mà bỏ qua exception startup.

**Ranh giới session:** Không dùng một `Session` đồng thời từ nhiều threads tùy ý; tạo sessions/consumers theo quy tắc JMS hoặc nhờ Spring listener container quản lý.

### 7.2. Simplified API JMSContext

```java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSContext;
import jakarta.jms.JMSConsumer;
import jakarta.jms.Queue;

public final class SelectorContextReceiver {

    private final ConnectionFactory connectionFactory;

    public SelectorContextReceiver(ConnectionFactory connectionFactory) {
        this.connectionFactory = connectionFactory;
    }

    public String pollSouth() {
        try (JMSContext context = connectionFactory.createContext(
                JMSContext.AUTO_ACKNOWLEDGE)) {

            Queue queue = context.createQueue("dispatch.jobs");
            JMSConsumer consumer =
                    context.createConsumer(queue, "region = 'SOUTH'");

            try {
                return consumer.receiveBody(String.class, 2_000L);
            } finally {
                consumer.close();
            }
        }
    }
}
```

`receiveBody` trả `null` nếu timeout, có thể ném runtime exception nếu body không chuyển được sang `String` hoặc provider gặp lỗi. Dạng simplified JMSContext mặc định `autoStart` khi tạo consumer, trừ khi ứng dụng thay đổi; không cần đồng thời dùng `context.start()` bừa bãi.

Số message `NORTH` trong queue không làm `pollSouth()` trả `NORTH`; nó chỉ có thể nhận message đủ điều kiện `SOUTH` theo API.

### 7.3. Producer phải đặt JMS property, không chỉ JSON field

```java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSContext;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;

public final class SelectorPropertyPublisher {

    private final ConnectionFactory cf;

    public SelectorPropertyPublisher(ConnectionFactory cf) {
        this.cf = cf;
    }

    public void send(String id, String region, int tier)
            throws jakarta.jms.JMSException {
        try (JMSContext context = cf.createContext()) {
            Queue queue = context.createQueue("dispatch.jobs");

            TextMessage message = context.createTextMessage(id);
            message.setStringProperty("region", region);
            message.setIntProperty("tier", tier);

            context.createProducer().send(queue, message);
        }
    }
}
```

Ví dụ tích hợp với broker. Để test “message không khớp”, có thể gửi `region="WEST"`, nhưng production nên validate `region` qua allowlist trước send hoặc có tuyến xử lý WEST hợp lệ.

**JMS property metadata** khác field trong body; `TextMessage.getText()` ở đây chỉ chứa ID. Nếu dùng Spring/Jackson converter tạo JSON body, bạn vẫn cần đặt JMS property được selector dùng bằng message post-processor hoặc cơ chế header mapping đúng.

## 8. Spring JMS: @JmsListener(selector) và tác động tới nhóm worker

Spring Framework có `@JmsListener(selector = "...")`. Annotation cung cấp **JMS selector** cho listener endpoint; container tạo consumer theo selector, thay vì xử lý filter sau khi listener đã lấy message.

### 8.1. Hai listener cùng queue nhưng lọc theo region

Giả định Spring Framework 6+ hoặc 7+, Java 17+, có dependency `spring-jms`, Jakarta Messaging provider, `ConnectionFactory` và queue `dispatch.jobs` hợp lệ. Ví dụ gồm nhiều file trong cùng project Spring, không chạy bằng JDK thuần.

**File `DispatchJmsConfiguration.java`:**

```java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;

@Configuration
@EnableJms
public class DispatchJmsConfiguration {

    @Bean("dispatchSender")
    public JmsTemplate dispatchSender(ConnectionFactory cf) {
        JmsTemplate template = new JmsTemplate(cf);
        template.setPubSubDomain(false); // String -> Queue
        return template;
    }

    @Bean("dispatchListenerFactory")
    public DefaultJmsListenerContainerFactory dispatchListenerFactory(
            ConnectionFactory cf) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(cf);
        factory.setPubSubDomain(false);
        factory.setSessionTransacted(true);
        factory.setConcurrency("1-4");
        return factory;
    }
}
```

`setSessionTransacted(true)` làm local JMS listener transaction được commit/rollback theo xử lý; khi handler fail, provider có thể redeliver. Nó **không biến selector thành cơ chế exactly-once business processing**, và cũng không tự gom database transaction với JMS.

**File `DispatchPublisher.java`:**

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
public class DispatchPublisher {
    private final JmsTemplate template;

    public DispatchPublisher(
            @Qualifier("dispatchSender") JmsTemplate template) {
        this.template = template;
    }

    public void dispatch(String jobId, String region) {
        template.send("dispatch.jobs", session -> {
            var message = session.createTextMessage(jobId);
            message.setStringProperty("region", region);
            return message;
        });
    }
}
```

Chọn `send(..., MessageCreator)` giúp dễ thấy `setStringProperty("region", ...)` đặt ở đâu. Với `convertAndSend`, bạn có thể dùng `MessagePostProcessor` để thêm property sau conversion. Đừng mong Spring tự biến một field `region` trong DTO thành JMS property theo selector.

**File `NorthDispatchWorker.java`:**

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class NorthDispatchWorker {

    @JmsListener(
            destination = "dispatch.jobs",
            selector = "region = 'NORTH'",
            containerFactory = "dispatchListenerFactory",
            concurrency = "2-4")
    public void handle(String jobId) {
        System.out.println("NORTH handled " + jobId);
    }
}
```

**File `SouthDispatchWorker.java`:**

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class SouthDispatchWorker {

    @JmsListener(
            destination = "dispatch.jobs",
            selector = "region = 'SOUTH'",
            containerFactory = "dispatchListenerFactory",
            concurrency = "1-2")
    public void handle(String jobId) {
        System.out.println("SOUTH handled " + jobId);
    }
}
```

Hai listener cùng một **Queue**. `concurrency` điều chỉnh phạm vi concurrent consumers của listener container (được provider/container hỗ trợ), nhưng **không đổi selector** và **không tạo một bản sao mỗi worker**.

Khi gọi:

```java
publisher.dispatch("JOB-1", "NORTH");
publisher.dispatch("JOB-2", "SOUTH");
publisher.dispatch("JOB-3", "WEST");
```

Nếu chỉ có hai loại listener này, broker hoạt động, queue hợp lệ, message không expired và consumer đã sẵn sàng, **có thể** thấy:

```text
NORTH handled JOB-1
SOUTH handled JOB-2
```

Thứ tự log không được bảo đảm. `JOB-3` **không được hai handler xử lý**, vì không match; nó có thể nằm trong queue, chờ policy hoặc một future consumer phù hợp. **Không suy ra `dispatch` thành công nghĩa là `JOB-3` đã xử lý.**

### 8.2. Điều gì xảy ra nếu tăng concurrency North?

Giả sử tăng North lên 8 instances:

- Có thể xử lý nhiều `region=NORTH` hơn nếu bottleneck thuộc consumer.
- **Không** tăng khả năng lấy `SOUTH` hoặc `WEST`.
- Nếu broker bị giới hạn scan/prefetch/quota, tăng threads chưa chắc làm thông lượng tăng tương ứng.
- Với một message NORTH, không phải cả 8 instance đều nhận; mỗi lần delivery vẫn chỉ một consumer.

Nếu 95% message là SOUTH nhưng hầu hết concurrency dành cho NORTH, việc cộng tổng threads có thể làm dashboard trông khỏe nhưng backlog SOUTH vẫn tăng.

### 8.3. Đừng filter bên trong handler nếu mục đích là để broker giữ message cho nhóm khác

Anti-pattern:

```java
@JmsListener(destination = "dispatch.jobs")
public void handle(String jobId) {
    if (!belongsToNorth(jobId)) {
        return;
    }
    processNorth(jobId);
}
```

Đây là **pseudocode nghiệp vụ**, không phải ví dụ có đủ method để biên dịch; mục đích chỉ ra lỗi thiết kế. Listener không có selector đã **tiêu thụ message** và khi method return thành công có thể ACK/commit. Message thuộc SOUTH có thể bị xóa khỏi queue mà SouthWorker không bao giờ thấy.

**Đúng hơn:** dùng selector ở JMS consumer khi cần cạnh tranh xử lý từng loại, hoặc một broker/application router phân loại message tới nhiều queue riêng.

### 8.4. Selector và destination type không thay thế nhau

`selector` hoạt động trong cả queue/topic domain. Spring phải resolve đúng loại destination, ví dụ `factory.setPubSubDomain(false)` cho queue và `true` cho topic. Nếu producer gửi Queue nhưng listener được cấu hình Topic cùng tên, không thể sửa bằng việc viết selector rộng hơn.

### 8.5. Static selector và cập nhật cấu hình

`@JmsListener(selector = "...")` là cấu hình khi endpoint được đăng ký. Thay giá trị selector trong source/config có thể yêu cầu container **dừng và tạo lại consumer**; không có bảo đảm thay đổi “nóng” biểu thức của một consumer đã tạo mà vẫn giữ các in-flight messages y nguyên.

Với durable subscription trên Topic, thay selector còn có thể tương đương **recreate subscription** và ảnh hưởng backlog. Cần quy trình rollout/migration, không chỉ deploy biểu thức mới.

## 9. Spring: ví dụ Topic với hai selector và backlog riêng

Giả sử Topic `orders.events` có hai trách nhiệm:

- Audit chỉ quan tâm `kind = 'INVOICE'`.
- Metrics chỉ quan tâm `amount >= 1000`.

Trước tiên tạo topic listener factory riêng:

```java
@Bean("topicListenerFactory")
public DefaultJmsListenerContainerFactory topicListenerFactory(
        ConnectionFactory cf) {
    var factory = new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(cf);
    factory.setPubSubDomain(true);
    factory.setSessionTransacted(true);
    return factory;
}
```

Đây là **@Bean method trong configuration class**, phải import các kiểu Spring/JMS như ví dụ config trước và broker đã provision topic. Không phải file Java standalone.

**Listener Audit:**

```java
@JmsListener(
        destination = "orders.events",
        selector = "kind = 'INVOICE'",
        containerFactory = "topicListenerFactory")
public void auditInvoice(String payload) {
    // Xử lý một bản sao phù hợp của subscription Audit.
}
```

**Listener Metrics:**

```java
@JmsListener(
        destination = "orders.events",
        selector = "amount >= 1000",
        containerFactory = "topicListenerFactory")
public void recordLargeOrder(String payload) {
    // Xử lý một bản sao phù hợp của subscription Metrics.
}
```

Hai method là các mảnh trong các Spring managed components hợp lệ; chúng **không phải cùng một listener**. Producer phải đặt properties `kind` và `amount` trên JMS Message, không chỉ để số tiền trong JSON body. Khi cùng event khớp cả hai selector, hai subscription độc lập có thể nhận **mỗi bên một bản**. Khi event không khớp Audit, nó **không tạo backlog Audit**.

### 9.1. Nếu muốn durable backlog cho Audit

Phương án khái niệm với subscription bền vững:

```java
@Bean("durableAuditTopicFactory")
public DefaultJmsListenerContainerFactory durableAuditTopicFactory(
        ConnectionFactory cf) {
    var factory = new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(cf);
    factory.setPubSubDomain(true);
    factory.setSubscriptionDurable(true);
    factory.setClientId("audit-service");
    factory.setConcurrency("1");
    factory.setSessionTransacted(true);
    return factory;
}
```

```java
@JmsListener(
        destination = "orders.events",
        selector = "kind = 'INVOICE'",
        subscription = "audit-invoices-v1",
        containerFactory = "durableAuditTopicFactory")
public void durableAudit(String event) {
    // Chỉ matched events có thể vào durable backlog.
}
```

Đây là các mảnh config trong Spring project; cần phân biệt **unshared durable** với **shared durable** theo provider và quy tắc danh tính. Không chạy nhiều replica dùng chung client ID unshared như một queue worker group. Nếu muốn scale nhiều consumer cho **cùng một durable subscription**, tìm hiểu shared durable support, subscription identity và cấu hình `subscriptionShared` tương ứng; không tự tạo nhiều subscription độc lập rồi mong tránh duplication.

**Khi audit service offline:** matched events có thể vào backlog của durable subscription (theo expiration, delivery và broker policy); event không khớp selector không phải “chờ service đổi filter”.

## 10. Java 17 chạy độc lập: thấy rõ pending sau khi lọc

Ví dụ chạy thuần JDK 17, **mô phỏng semantics queue** bằng danh sách. Nó cho thấy nếu worker chỉ lấy item khớp, các item khác còn pending. Đây **không phải implementation JMS/broker**: không có transaction, acknowledgment, prefetch, priority, expiration, network hay concurrency.

Tạo file **`SelectorBacklogDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

public final class SelectorBacklogDemo {
    record Task(String id, String region) {}

    static List<Task> consumeMatching(List<Task> pending, String region) {
        List<Task> received = new ArrayList<>();

        for (Iterator<Task> iterator = pending.iterator();
                iterator.hasNext();) {

            Task task = iterator.next();
            if (region.equals(task.region())) {
                received.add(task);
                iterator.remove();
            }
        }
        return received;
    }

    static String ids(List<Task> tasks) {
        return tasks.stream().map(Task::id).toList().toString();
    }

    public static void main(String[] args) {
        List<Task> queue = new ArrayList<>(List.of(
                new Task("N-1", "NORTH"),
                new Task("W-1", "WEST"),
                new Task("S-1", "SOUTH"),
                new Task("N-2", "NORTH"),
                new Task("M-1", null)
        ));

        List<Task> north = consumeMatching(queue, "NORTH");
        List<Task> south = consumeMatching(queue, "SOUTH");

        System.out.println("NORTH consumed: " + ids(north));
        System.out.println("SOUTH consumed: " + ids(south));
        System.out.println("Queue pending: " + ids(queue));

        List<Task> west = consumeMatching(queue, "WEST");
        System.out.println("WEST consumed: " + ids(west));
        System.out.println("Queue pending after WEST: " + ids(queue));
    }
}
```

Chạy:

```bash
javac SelectorBacklogDemo.java
java SelectorBacklogDemo
```

**Stdout chính xác:**

```text
NORTH consumed: [N-1, N-2]
SOUTH consumed: [S-1]
Queue pending: [W-1, M-1]
WEST consumed: [W-1]
Queue pending after WEST: [M-1]
```

Giải thích:

- Hai nhóm North/South đều xử lý hoàn tất phần đủ điều kiện.
- `W-1` và `M-1` vẫn tồn ở queue mô phỏng; không có logic tự chuyển chúng sang DLQ.
- Sau khi thêm West consumer, `W-1` có thể được lấy. `M-1` thiếu region vẫn còn pending.
- Trong JMS thật, message thiếu property `region` được xử lý theo **SQL NULL semantics**, không theo `Task.region == null` của Java; ví dụ thuần Java chỉ mô phỏng kết quả cho selector bằng nhau.
- Việc lập danh sách ở đây diễn ra tuần tự, nên stdout có thứ tự cố định; trên broker thật với nhiều consumers, không suy ra thứ tự xử lý và worker nhận message bằng demo này.

### 10.1. Mở rộng tư duy cho overlapping selectors

Nếu thay `South` bằng consumer có điều kiện `tier >= 3` và một message NORTH đồng thời tier 3, mô phỏng phải chọn **một** trong hai consumer lấy message đó, chứ không copy thành hai bản. Nếu bài toán yêu cầu cả NorthHandler và VipHandler xử lý, cần thêm một abstraction event fan-out/subscriptions.

### 10.2. Mở rộng tư duy cho Topic

Đối với Topic, thay vì một list queue chung, mỗi subscription sẽ có danh sách pending **độc lập chỉ với events phù hợp selector**. Event khớp hai sub được copy vào hai list. Event không khớp một sub không được thêm vào list đó; không có item đợi sub đổi selector.

## 11. Khi nào selector phù hợp và khi nào nên chia queue?

### Giữ một queue, nhiều selector khi:

- Số nhóm nhỏ, tương đối ổn định và metadata routing được validate.
- Các nhóm dùng cùng một logical work stream nhưng phân trách nhiệm theo partition.
- Broker hỗ trợ matching/dispatch đủ tốt với backlog/traffic hiện tại.
- Có metrics và runbook cho message unmatched.
- Nếu có consumer overlap, mọi consumer được phép làm **cùng một business action**; không cần fan-out đa nghiệp vụ.

### Tạo queue riêng theo nhóm khi:

- Các nhóm có SLO, capacity hoặc retry/DLQ khác biệt rõ.
- Có nguy cơ queue chung tích lũy nhiều message không có matching consumer.
- Muốn đo pending/oldest age và scale worker **theo nhóm** dễ dàng.
- Phân quyền, isolation/tenant, quota hoặc compliance yêu cầu tách.
- Broker có chi phí scan/prefetch lớn với nhiều selectors phức tạp.
- Muốn deploy nhóm A mà không ảnh hưởng quá nhiều tới backlog nhóm B.

Ví dụ:

```text
Producer / router
   |
   +-- dispatch.north.jobs --> North workers
   |
   +-- dispatch.south.jobs --> South workers
   |
   +-- dispatch.invalid    --> triage / alert / remediation
```

Tách queue làm phần routing chuyển sang phía producer/router, **không loại bỏ nhu cầu validate**. Routing lỗi có thể khiến message đi vào sai queue và vẫn tạo backlog. Thêm queue cũng tăng chi phí quản trị; cân nhắc lượng traffic, topology và chính sách broker.

### Dùng Topic với nhiều subscription khi:

- Một event cần nhiều dịch vụ độc lập đều nhận và xử lý.
- Mỗi subscription có selector riêng và cần kiểm soát backlog độc lập.
- Có yêu cầu subscriber offline nhận lại event → durable subscription phù hợp.
- Một nhóm cần scale worker tiêu thụ **cùng một subscription** → shared subscription, nếu provider hỗ trợ và cấu hình đúng.

**Không sửa bài toán fan-out bằng hai consumer có selector chồng lấn trên queue.** Đó vẫn là competing consumers.

## 12. Runbook: queue tăng backlog nhưng worker vẫn “healthy”

Để tìm nguyên nhân, thực hiện theo thứ tự sau.

### Bước 1 — Xác nhận nguồn và đích

- Tên destination, type Queue/Topic, provider namespace/vhost.
- Producer gửi vào đâu, có bị resolve nhầm queue/topic do `pubSubDomain` không?
- Queue depth/ready count/in-flight count tăng từ khi nào?
- Consumer count có thật sự ở trên **destination đúng** không?

### Bước 2 — Thu thập selector đang active

- Mỗi listener/container có selector gì, phiên bản config nào?
- Có missing consumers sau rollout hoặc crash?
- Có selector mặc định rỗng (match tất cả) vô tình cạnh tranh nhận không?
- Có hai selector overlap làm phân tải khác mong đợi?
- Với Topic, xem **subscription identity** và selector tại subscription, không chỉ xem tên topic.

### Bước 3 — Xem metadata của các message đang pending

Chọn mẫu message qua broker console, admin API hoặc `QueueBrowser` nếu phù hợp:

- JMS property names: `region` hay `Region`?
- JMS property types: int vs String, boolean vs String?
- Values: `NORTH`, `SOUTH`, `WEST`, null/missing?
- Message đã expired hoặc có delivery delay?
- JMSPriority, transaction, ack/redelivery và pending/in-flight?

**Không dùng consumer không selector chỉ để “đọc thử”** nếu nó có thể ACK message hợp lệ. Dùng đường browse/management không tiêu thụ. JMS `QueueBrowser` có thể xem message mà không remove, nhưng việc browser có thấy snapshot toàn queue, phân trang, chi phí quét ra sao phụ thuộc provider và workload; tránh duyệt hàng triệu message không giới hạn.

### Bước 4 — Xác định nhóm nào đang không khớp

Lập bảng:

| Message category | Matching consumers | Incoming rate | Completion rate | Oldest age |
| --- | ---: | ---: | ---: | --- |
| NORTH | 4 | ... | ... | ... |
| SOUTH | 2 | ... | ... | ... |
| WEST | 0 | ... | 0 | ... |
| Missing/invalid | 0 | ... | 0 | ... |

Trong ví dụ, “WEST: zero matching consumers” là phát hiện quan trọng hơn “6 consumers connected”. JMS API **không chuẩn hóa một API đếm pending theo selector** cho mọi broker; có thể phải dùng broker management, sampling hoặc application observability phù hợp.

### Bước 5 — Phân loại hành động khắc phục

- **Thiếu worker hợp lệ:** tăng capacity cho đúng selector hoặc tạo worker mới hợp đồng nghiệp vụ.
- **Producer gửi region sai:** sửa validation/routing, tạo policy xử lý các message đã tồn một cách có kiểm soát.
- **Selector so sánh sai kiểu:** chuẩn hóa JMS property setters và test compatibility.
- **Overlap sai kiến trúc:** tách queue/Topic subscription, không phụ thuộc cách broker giành message.
- **Consumer quá chậm:** profile business I/O, DB locks, transaction latency, prefetch và concurrency theo provider.
- **Payload lỗi cố định:** cơ chế poison-message retry/DLQ, không mở rộng selector để nuốt lỗi schema.
- **Broker quota gần đầy:** alert/scale storage hoặc xử lý backlog theo nghiệp vụ; không xóa message bừa bãi.
- **Topic durable sai selector:** sửa qua kế hoạch subscription migration, chú ý state/backlog và event lost risk.

### Bước 6 — Theo dõi sau sửa

Đo queue depth và **oldest age** giảm đúng như mong đợi; đếm completed business IDs, tránh duplicate side effects; xác minh không tạo unfiltered consumer thu gom nhầm message của nhóm khác. Với Topic, đo **subscription backlog** theo sub thay vì chỉ publish throughput.

## 13. Kiểm thử integration cần có

### Test A — Queue: message không khớp vẫn còn

1. Provision `dispatch.jobs` ở môi trường test.
2. Khởi động chỉ North/South listeners với selectors.
3. Gửi `NORTH`, `SOUTH`, `WEST` và một message thiếu `region`.
4. Xác minh North/South xử lý đúng message thuộc nhóm.
5. Kiểm tra `WEST` và missing vẫn pending (trong giả định không có TTL/expiry/cleanup policy khác).
6. Khởi động West consumer phù hợp và xác minh nó có thể xử lý message WEST pending.

### Test B — Overlapping selectors trên Queue

1. Worker A: `region='NORTH'`.
2. Worker B: `tier >= 3`.
3. Gửi message `region=NORTH,tier=3` với business ID.
4. Xác minh nó **không được fan-out cho cả hai** vì queue; mỗi lần delivery một consumer.
5. Cố ý rollback để thấy redelivery có thể xảy ra, khẳng định business idempotency phải tách.

### Test C — NULL/type/case

1. Gửi message thiếu `region`, rồi property `Region` (R viết hoa), rồi `region='north'`.
2. So với selector `region = 'NORTH'`.
3. Kiểm tra chỉ message đúng tên/case/giá trị mới match.
4. Thử `region IS NULL` và xác minh những message thiếu property được chọn.
5. Gửi `tier` bằng `setStringProperty("tier", "3")` và `setIntProperty("tier",3)`; kiểm tra `tier >= 2` chỉ đúng với numeric property theo chuẩn.
6. Thử expression invalid; ghi nhận startup `InvalidSelectorException`/runtime exception thích hợp.

### Test D — Topic subscriptions

1. Tạo hai subscription riêng với selectors tương ứng.
2. Publish E1 khớp cả hai, E2 chỉ khớp một, E3 không khớp bên nào.
3. Xác minh bản sao theo subscription, không suy luận “E2 vẫn nằm chờ trong mọi subscription”.
4. Với durable sub, dừng consumer rồi publish matched event, khởi động lại cùng identity; kiểm tra backlog theo delivery/expiration policy.
5. Thay selector durable trên test subscription và xác minh semantics recreate/migration của provider; **không làm trên production đang chứa event chưa xử lý**.

### Test E — Backlog và scale

1. Tạo tải North > capacity North, South < capacity South, thêm một phần WEST không matching.
2. Theo dõi backlog từng nhóm, thông lượng và oldest message age.
3. Tăng North concurrency, kiểm tra chỉ phần eligible North tăng throughput.
4. Thêm worker West, kiểm tra pending West giảm.
5. So sánh với tách queue `north`/`south`/`invalid` về isolation và metrics.

### Test F — Expiration, redelivery và DLQ

1. Gửi message `WEST` với TTL xác định vào queue không có West consumer.
2. Quan sát broker xử lý expired message theo policy (không suy ra tự DLQ bởi selector).
3. Gửi NORTH, cố ý throw trong handler, theo dõi rollback/redelivery.
4. Kiểm tra sự khác nhau giữa message **không eligible** và message **eligible nhưng xử lý lỗi** trong logs, counters và DLQ.
5. Dùng business ID để kiểm tra không tạo side effect trùng khi redelivery.

## 14. Những lỗi tư duy thường gặp

**Lỗi 1 — “Message không khớp selector sẽ bị drop ngay.”**  
Sai trên Queue theo semantics chung. Nó có thể nằm chờ hoặc được consumer khác nhận. Trên Topic, message không khớp **không được thêm vào subscription ấy**.

**Lỗi 2 — “Hai selector đều khớp nên hai worker queue đều nhận.”**  
Sai. Queue là competing consumers; trong mỗi lần delivery chỉ một consumer nhận.

**Lỗi 3 — “Tăng concurrency tổng sẽ giải quyết backlog.”**  
Không nếu message tồn thuộc nhóm không có matching consumer hoặc nhóm có capacity không được tăng.

**Lỗi 4 — “Không match thì JMS tự đẩy sang DLQ.”**  
Không có bảo đảm như vậy. DLQ/expiry/unroutable behavior là policy khác, tùy provider.

**Lỗi 5 — “region trong JSON đủ cho JMS selector.”**  
Không. Selector chuẩn không đọc body; phải có JMS property/header phù hợp.

**Lỗi 6 — “region <> 'NORTH' sẽ bắt missing region.”**  
Sai. Missing property đánh giá UNKNOWN; phải xử lý `IS NULL` nếu cần.

**Lỗi 7 — “setStringProperty('tier','3') giống setIntProperty('tier',3).”**  
Sai. Property types khác; so sánh numeric trong selector không tự parse String.

**Lỗi 8 — “Consumer không selector chỉ nhận phần còn dư sau các consumer có selector.”**  
Sai. Unfiltered consumer đủ điều kiện nhận mọi message; nó có thể giành việc của nhóm khác.

**Lỗi 9 — “Selector làm broker route như một hàm ưu tiên cố định.”**  
Sai. Selector chỉ xác định eligibility; broker tự phân phối giữa những consumer eligible theo semantics và policy.

**Lỗi 10 — “Queue backlog cao chứng minh mọi worker đều bận.”**  
Sai. Worker hợp lệ có thể rảnh nhưng pending thuộc nhóm khác/invalid. Phải đo theo category.

**Lỗi 11 — “Selector topic không khớp sẽ chờ đến khi subscriber đổi điều kiện.”**  
Sai. Message không được thêm vào subscription đó; không có replay từ trước theo chuẩn chỉ bằng đổi selector.

**Lỗi 12 — “Đổi selector durable không ảnh hưởng message đang tồn.”**  
Không được giả định. Thay selector có thể tương đương recreate subscription và mất state pending; cần migration.

**Lỗi 13 — “Listener filter sau khi nhận tương đương JMS selector.”**  
Không. Listener có thể đã consume/ack message trước khi return; điều đó làm nhóm khác không còn cơ hội nhận.

**Lỗi 14 — “Priority cao làm message không cần khớp selector.”**  
Sai. QoS priority không vượt qua filter: consumer chỉ được giao message đủ điều kiện.

**Lỗi 15 — “Có active consumers nghĩa là có consumer match mọi message.”**  
Sai. Consumer count không cho biết độ bao phủ selector trên thực tế.

**Lỗi 16 — “Một message không nhận trong 3 giây nghĩa là queue rỗng.”**  
Sai. `receive(timeout)` với selector có thể timeout ngay khi queue còn nhiều message không khớp.

**Lỗi 17 — “Topic thêm nhiều subscriber luôn tăng tốc cùng một tác vụ.”**  
Sai nếu mỗi subscriber là subscription độc lập: sẽ tạo thêm bản sao công việc. Để chia tải trong một subscription, dùng shared subscription nếu phù hợp.

## 15. Checklist thiết kế selector trước khi deploy

- [ ] **Chọn đúng semantics:** queue competing work hay topic fan-out?
- [ ] **Định nghĩa routing properties:** tên, kiểu, giá trị hợp lệ, default/null handling và version.
- [ ] **Kiểm chứng producer:** set JMS properties thực, không chỉ serialize field vào JSON.
- [ ] **Kiểm tra selector:** cú pháp SQL92-subset, case-sensitive identifiers, TRUE/FALSE/UNKNOWN và precedence.
- [ ] **Bao phủ nhóm:** message hợp lệ nào cũng có ít nhất một consumer có khả năng xử lý?
- [ ] **Chồng lấn:** message có thể match nhiều consumer queue; điều đó có làm sai business effect không?
- [ ] **Xử lý invalid:** không gửi vào queue chung nếu không có consumer phụ trách; có validation/invalid queue/triage.
- [ ] **Tính capacity theo nhóm:** arrival rate, service time, concurrency và backlog growth riêng.
- [ ] **Bảo vệ broker:** quota, TTL, retention, DLQ và tài nguyên khi message unmatched tích lũy.
- [ ] **Theo dõi tuổi message:** không chỉ queue depth tổng; có oldest age và consumer idle/busy theo nhóm.
- [ ] **Prefetch/priority:** đã kiểm thử provider-specific interaction, không giả định strict FIFO/head-of-line.
- [ ] **Listener factory:** pubSubDomain, selector, concurrency, transaction và redelivery đúng.
- [ ] **Topic subscription:** durable/non-durable, shared/unshared, identity và selectors rõ ràng.
- [ ] **Rollout:** thay selector/topic sub có kế hoạch migration/backlog, không silently reset durable state.
- [ ] **Failure tests:** timeout receive, missing property, wrong type, invalid expression, consumer stop, dead-letter, expiration.
- [ ] **Idempotency:** business ID và deduplication khi message bị redeliver.
- [ ] **Security:** JMS properties từ untrusted producer không được coi là authorization; xác thực và ACL ở broker.
- [ ] **Test end-to-end:** đo producer accepted, broker pending, matched deliveries và completed business action.

## 16. Tự kiểm tra kiến thức

**Câu 1.** Hai consumer trên cùng queue có selectors `region='NORTH'` và `region='SOUTH'`. Message có property `region='WEST'`. Theo JMS, chuyện gì có thể xảy ra?

**Đáp án:** Không consumer nào đủ điều kiện. Message có thể tiếp tục nằm trong queue đến khi có consumer phù hợp hoặc chính sách expiry/management tác động; không tự DLQ chỉ vì không match.

**Câu 2.** Hai consumer Queue có selectors chồng lấn, cùng khớp một message. Họ có mỗi người nhận một bản sao không?

**Đáp án:** Không. Trên Queue, mỗi lần delivery chỉ một consumer nhận. Redelivery có thể xảy ra sau rollback/ack failure, không phải fan-out nghiệp vụ.

**Câu 3.** Body chứa JSON `{"region":"NORTH"}`, JMS property `region` không tồn tại. Selector `region='NORTH'` có khớp không?

**Đáp án:** Không. Selector không đọc body JSON, missing property dẫn đến UNKNOWN/không match.

**Câu 4.** Vì sao tăng số worker NORTH không làm backlog WEST giảm?

**Đáp án:** Tất cả worker NORTH đều có selector chỉ chấp nhận NORTH; WEST không eligible. Tăng capacity sai nhóm không giúp.

**Câu 5.** `region <> 'NORTH'` có bắt property `region` thiếu không?

**Đáp án:** Không, vì so sánh với NULL là UNKNOWN; cần `region IS NULL` nếu muốn bắt missing.

**Câu 6.** `tier` được set kiểu String `"3"`, selector `tier >= 2` có tự ép kiểu sang số không?

**Đáp án:** Không được dựa vào auto String→numeric conversion. Dùng `setIntProperty("tier",3)` và test đúng schema.

**Câu 7.** Một unfiltered consumer được thêm vào queue đang có North/South selectors. Nó có chỉ nhận WEST không?

**Đáp án:** Không. Nó eligible cho mọi message, có thể giành message NORTH/SOUTH.

**Câu 8.** Topic có Audit subscription selector `kind='INVOICE'` và Metrics selector `amount>=1000`. Một event khớp cả hai được xử lý thế nào?

**Đáp án:** Mỗi subscription độc lập có thể nhận một bản sao. Ack/commit độc lập.

**Câu 9.** Một message không khớp selector của durable subscription có nằm chờ trong backlog subscription đó không?

**Đáp án:** Không. Selector quyết định message nào được thêm vào subscription; không match thì không tạo bản sao.

**Câu 10.** Thay selector unshared durable subscription với cùng identity và không có consumer active có thể tương đương thao tác gì?

**Đáp án:** Theo Jakarta Messaging, thay topic/selector/noLocal có thể tương đương xóa subscription cũ và tạo mới; cần bảo vệ/migration backlog.

**Câu 11.** `@JmsListener(selector="region='NORTH'")` lọc trước hay sau khi Spring method nhận message?

**Đáp án:** JMS provider/consumer áp dụng filter trước khi giao message eligible cho listener. Khác với `if` rồi return trong handler.

**Câu 12.** Queue depth cao, South consumer rảnh, North xử lý hết capacity. Tại sao?

**Đáp án:** Selector phân đoạn eligibility; South không được phép nhận North; cần scale đúng North hoặc thay kiến trúc routing.

**Câu 13.** `receive(3000)` của North consumer trả null, vậy queue chắc chắn trống?

**Đáp án:** Không. Có thể queue chứa toàn SOUTH/WEST/missing hoặc có message chưa eligible vì điều kiện khác.

**Câu 14.** Selector có thể tham chiếu tùy ý `JMSExpiration` hay `JMSDestination` theo JMS chuẩn không?

**Đáp án:** Không. Danh sách standard header fields có thể dùng trong selector bị giới hạn; hãy dùng một application property hợp lệ nếu cần metadata riêng.

**Câu 15.** Trên Topic, hai consumer dùng chung **shared durable subscription** có mỗi người nhận mọi matched event không?

**Đáp án:** Không. Họ chia những message của **một subscription**; mỗi message thuộc subscription được giao một consumer trong nhóm tại mỗi lần delivery.

**Câu 16.** Message không có matching consumer trên queue có mặc định đi DLQ không?

**Đáp án:** Không có bảo đảm chung; DLQ phụ thuộc provider retry/expiry/unroutable policy. Unmatched không đồng nghĩa failed processing.

**Câu 17.** Metric nào giúp nhận ra backlog do không có matching consumer?

**Đáp án:** Pending/oldest age theo category, property sampling, active selectors, matching consumer count, arrival/completion rate, broker pending/in-flight/expired counters; chỉ xem tổng consumer count là không đủ.

**Câu 18.** Khi nào nên chọn nhiều queue thay vì một queue có nhiều selector?

**Đáp án:** Khi cần isolation/capacity/retention/ACL/metrics/SLAs riêng, selector coverage khó kiểm soát, hoặc broker không hoạt động tốt với nhiều unmatched/complex selectors.

## Tóm tắt trọng tâm

- **Selector quyết định eligibility, không tự làm load balancing.** Trên Queue, nhiều matching consumers cạnh tranh nhận **một** message; không matching thì message có thể tiếp tục tồn.
- **Queue backlog có thể tăng dù consumer vẫn khỏe** nếu capacity lệch nhóm, selector không bao phủ tất cả message, property sai kiểu/case hoặc không có consumer phù hợp.
- **Topic selector hoạt động theo subscription**: chỉ matched messages mới được thêm vào từng subscription; non-matching events không chờ trong subscription để được đọc lại về sau.
- **Durable subscription chỉ giữ những message phù hợp selector của nó** theo delivery/expiry rules; sửa selector có thể làm thay đổi hoặc tạo lại state subscription.
- **JMS selector không đọc body**; dùng JMS properties/header phù hợp, SQL92-subset và three-valued logic (`TRUE`/`FALSE`/`UNKNOWN`).
- **Spring `@JmsListener(selector)` là server/provider-side eligibility**, không giống filter sau khi handler đã ACK message.
- **Đo theo nhóm**, không chỉ queue depth hay consumer count tổng; thiết kế fallback, invalid routing, observability và tách queue khi cần.

### Tài liệu tham khảo chính thức

1. [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html) — mục `3.8 Message selection`, `4.1.2 Queue semantics`, `4.2.2 Topic semantics`, `8.2` và `8.3` (durable/shared subscriptions).
2. [Jakarta Messaging 3.1 — Message API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message) — property types, selector SQL92-subset, NULL/UNKNOWN và những standard headers được phép.
3. [Jakarta Messaging 3.1 — Session API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/session) — `createConsumer(destination, selector)` và durable consumer APIs.
4. [Jakarta Messaging 3.1 — JMSContext API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/jmscontext) — `createConsumer(destination, selector)` trong simplified JMS.
5. [Spring Framework — @JmsListener Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/annotation/JmsListener.html) — `selector`, `destination`, `containerFactory`, `subscription` và `concurrency`.
6. [Spring Framework — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html) — listener factory, `@EnableJms`, container lifecycle và method arguments.
7. [Spring Framework — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html) — destination resolution, queue/topic domain, listener containers và session transactions.
