# Thiết kế bộ lọc và định tuyến message trong Service Bus

> **Chương:** Hàng đợi và thông điệp  
> **Module:** `CLOUD_PROVIDERS_AZURE` — Khám phá hệ sinh thái Microsoft Azure từ subscription, resource group và Entra ID đến mạng ảo, dịch vụ tính toán, lưu trữ và dữ liệu. Học cách triển khai, giám sát, bảo vệ và kiểm soát chi phí một kiến trúc ứng dụng trên Azure.

## Mục tiêu bài học

Sau bài học, bạn có thể:

1. Phân biệt **queue**, **topic**, **subscription**, **message**, **rule/filter** và **SQL rule action** trong Azure Service Bus.
2. Thiết kế mô hình publish/subscribe để một sự kiện tới đúng các nhóm consumer mà không phải nhân bản logic định tuyến ở publisher.
3. Viết và đọc **SQL filter** cho application properties, phân biệt điều kiện `AND`/`OR`, kiểu dữ liệu và thuộc tính thiếu.
4. Dùng **correlation filter** khi điều kiện là so khớp chính xác trên một số property.
5. Hiểu rule mặc định **`$Default`**, quy tắc kết hợp nhiều rules, xử lý rule chồng lấn và rủi ro nhận thừa.
6. Xây dựng và thử nghiệm ba subscription: giao hàng, kiểm tra gian lận và kiểm toán, cùng tập message có kết quả mong đợi.
7. Kiểm soát **rule lifecycle**, giao tiếp an toàn, phân quyền, dead-letter, idempotency và auto-forwarding.
8. Giám sát, chẩn đoán và tối ưu hiệu năng/chi phí trước khi đưa hệ thống Service Bus vào production.

## 1. Bối cảnh: một sự kiện, nhiều người tiêu thụ

Một hệ thống bán hàng phát sinh sự kiện khi có đơn mới:

~~~json
{
  "orderId": "ORD-1001",
  "customerId": "CUS-21",
  "totalAmount": 12500000,
  "items": [{"sku": "A1", "quantity": 1}]
}
~~~

Các hệ thống phía sau có nhu cầu khác nhau:

- **Fulfillment** chỉ tiếp nhận đơn được tạo tại thị trường Việt Nam để chuẩn bị giao hàng.
- **Fraud detection** tiếp nhận đơn giá trị cao để kiểm tra.
- **Audit** muốn lưu vết tất cả sự kiện đơn hàng.

Nếu publisher gửi ba request riêng đến ba service, publisher sẽ phải biết người nhận, quản lý nhiều endpoint và xử lý lỗi gửi lặp. Đây là *point-to-point coupling* khiến việc thêm consumer mới tốn công sửa ứng dụng gửi.

Thay vào đó, publisher gửi **một message tới Azure Service Bus Topic**. Mỗi nhóm consumer có **subscription riêng** và tự thiết kế rule lọc:

~~~mermaid
flowchart LR
    P["Order API\nPublisher"]
    T["Topic\norders.events"]
    F["Subscription\nfulfillment-vn\nVN + OrderCreated"]
    R["Subscription\nfraud-review\nHigh-value orders"]
    A["Subscription\naudit-all\nAll events"]
    C1["Fulfillment Worker"]
    C2["Fraud Worker"]
    C3["Audit Worker"]
    P -->|"1 event + properties"| T
    T -->|"SQL/Correlation rule"| F --> C1
    T -->|"SQL rule"| R --> C2
    T -->|"$Default True"| A --> C3
~~~

Điểm quan trọng: **topic không phải hàng đợi chung được ba consumer cạnh tranh đọc**. Với một topic, **mỗi subscription là một luồng lưu trữ/nhận message riêng**, độc lập về tiến độ và dead-letter. Một message có thể được gửi tới **nhiều subscriptions** nếu nó khớp nhiều bộ lọc.

## 2. Phân biệt Queue, Topic, Subscription, Rule và Message

| Thành phần | Vai trò | Điều cần nhớ |
| --- | --- | --- |
| **Queue** | Point-to-point: một queue, nhiều competing consumers | Thông thường một message được một receiver xử lý tại một thời điểm qua lock |
| **Topic** | Nơi publisher gửi sự kiện để fan-out | Publisher không gửi trực tiếp đến từng subscription |
| **Subscription** | Luồng message độc lập gắn với topic | Có rules, TTL, lock, DLQ và consumer riêng |
| **Rule** | Điều kiện filter và có thể có action | Xác định message nào được chọn vào subscription |
| **SQL filter** | Biểu thức logic trên các message properties được hỗ trợ | Dùng `AND`/`OR`, so sánh, `IN`, `LIKE` khi cần |
| **Correlation filter** | So khớp bằng equality các property chỉ định | Hiệu quả với matching đơn giản; không phải query body JSON |
| **Application properties** | Metadata do publisher cung cấp | Ví dụ `eventType`, `region`, `amount` |
| **System properties** | Metadata chuẩn của message | Ví dụ `MessageId`, `CorrelationId`, `Subject`, `SessionId` |
| **SQL action** | Tác vụ biến đổi property cho message khi rule phù hợp | Không thay thế consumer business logic |
| **DLQ** | Dead-letter subqueue cho message không thể xử lý | *Không khớp rule* không đồng nghĩa tự vào DLQ |

### 2.1. Topic/Subscription khác consumer group trong Event Hubs

Azure Service Bus Topic phù hợp brokered business messaging: queue semantics, sessions, duplicate detection, dead-letter, lock, transactions và routing rules. Azure Event Hubs tập trung vào streaming với partitions/offsets/consumer groups; không nên dùng hai khái niệm thay thế cho nhau.

### 2.2. Tính năng theo tier

Azure Service Bus có các tier **Basic, Standard và Premium**. **Topics và subscriptions không thuộc khả năng của Basic**; cần chọn Standard hoặc Premium theo nhu cầu. Premium có mô hình tài nguyên/công suất riêng, phù hợp khi cần isolation và hiệu năng ổn định hơn, nhưng phải tính phí và quota tương ứng.

Giới hạn về số rules, subscriptions, message size, throughput, networking và feature availability phải đối chiếu với **tier, region và API/SDK hiện hành**. Không thiết kế dựa trên hạn mức lấy từ tier khác.

### 2.3. Một message có body và metadata tách biệt

Trong Service Bus, body có thể là JSON, Avro, Protobuf hoặc bytes; **subscription SQL filter không duyệt tùy ý vào JSON body**. Nếu muốn route theo vùng/loại nghiệp vụ, publisher cần đặt những giá trị dùng cho routing thành **application properties** có kiểu dữ liệu phù hợp.

Ví dụ cùng một message:

~~~text
Body:
  {"orderId":"ORD-1001","totalAmount":12500000}

Application properties:
  eventType = "OrderCreated"         (string)
  region    = "VN"                   (string)
  amount    = 12500000               (integer)
  priority  = 9                      (integer)
  schemaVer = 1                      (integer)

System properties:
  MessageId = "evt-ORD-1001-created-v1"
  CorrelationId = "checkout-9ab"
  Subject = "OrderCreated"
~~~

Nếu chỉ ghi `region` và `amount` bên trong body, rule `region = 'VN'` có thể không khớp vì broker không tự parse JSON để tạo application properties.

## 3. Luồng định tuyến ở broker

~~~mermaid
sequenceDiagram
    participant PUB as Publisher
    participant TOPIC as orders.events Topic
    participant RULES as Filter engine
    participant F as fulfillment-vn
    participant R as fraud-review
    participant A as audit-all
    participant CON as Consumer
    PUB->>TOPIC: Send(body + application properties)
    TOPIC->>RULES: Evaluate subscriptions/rules
    RULES->>F: Copy if fulfillment matches
    RULES->>R: Copy if fraud matches
    RULES->>A: Copy if audit matches
    CON->>F: Receive PeekLock
    F-->>CON: Message
    CON->>F: Complete after processing
~~~

Có ba thời điểm riêng biệt:

1. **Publish time:** broker quyết định message có được chuyển vào từng subscription dựa trên rules đang có.
2. **Receive time:** consumer đọc message đã được chọn vào subscription. Bộ lọc không được đánh giá lại như một query trên kho dữ liệu khi consumer nhận.
3. **Settlement:** consumer `Complete`, `Abandon`, `DeadLetter` hoặc để lock hết hạn theo quy trình. Bước này khác với routing filter.

**Thay rule hôm nay không tự động quét và lọc lại những message đã nằm sẵn trong subscription.** Với thay đổi chính sách routing, cần kế hoạch cutover, quan sát backlog và xử lý dữ liệu cũ rõ ràng.

### 3.1. Routing là fan-out có điều kiện

Một đơn hàng Việt Nam giá trị cao có thể khớp cả fulfillment, fraud và audit. Đây là kết quả **đúng** khi ba subscription mang ba mục đích độc lập.

### 3.2. Không khớp rule không phải là lỗi consumer

Nếu một message không khớp bất kỳ rule nào của `fulfillment-vn`, broker không đưa message đó vào subscription này. Không có message ở receiver **không nhất thiết là Service Bus bị mất message**; có thể filter đã loại đúng theo thiết kế.

Cần phân biệt:

- Không match: không được chọn vào subscription.
- Match nhưng không nhận: backlog, quyền, connection, consumer hoặc session issue.
- Đã nhận nhưng xử lý lỗi: retry, delivery count và DLQ theo chính sách.
- **Filter evaluation error**: cơ chế xử lý riêng, cần kiểm tra cấu hình dead-letter on filter evaluation exceptions và logs theo khả năng hỗ trợ.

## 4. Thiết kế metadata trước khi viết filter

### 4.1. Một hợp đồng message tối thiểu

Định nghĩa schema metadata trước, ví dụ:

| Property | Kiểu mong đợi | Ví dụ | Dùng ở rule? |
| --- | --- | --- | --- |
| `eventType` | string | `OrderCreated` | Có |
| `region` | string | `VN` | Có |
| `amount` | integer | `12500000` | Có |
| `priority` | integer | `9` | Có |
| `schemaVer` | integer | `1` | Có thể |
| `tenantKey` | string | `tenant-02` | Có thể khi phân tenant |
| `correlationId` (app-defined nếu có) | string | `flow-123` | Thường để tracing; tránh nhầm system CorrelationId |
| `MessageId` (system) | string | `evt-...` | Dedup/tracing |
| `CorrelationId` (system) | string | `checkout-9ab` | Tracing/correlation filter khi cần |

**Hợp đồng metadata là một phần của hợp đồng sự kiện.** Producer và consumers phải thống nhất tên property, chữ hoa/thường, kiểu dữ liệu, miền giá trị và ý nghĩa business.

### 4.2. Kiểu dữ liệu làm thay đổi kết quả lọc

Hai messages nhìn tương tự nhưng có thể khác:

~~~text
Message A: amount = 12500000      (integer)
Message B: amount = "12500000"    (string)
~~~

Filter `amount >= 10000000` được viết để so sánh **giá trị số**. Nếu publisher gửi chuỗi, kết quả có thể không như mong đợi hoặc xảy ra lỗi kiểu tùy biểu thức và semantics. Không dựa vào ép kiểu ngầm không được kiểm chứng.

**Quy tắc tốt:** chuẩn hóa metadata ở publisher; viết integration tests cho từng biến thể; không để producers tự đặt `amount` lúc string, lúc integer.

### 4.3. Version hóa metadata

Nếu đổi `eventType="OrderCreated"` thành `event_type="order.created"`, các rules cũ có thể không match. Một kế hoạch nâng cấp:

1. Thêm schema version rõ ràng (`schemaVer`).
2. Cập nhật rules để chấp nhận đồng thời event cũ/mới trong giai đoạn chuyển tiếp.
3. Triển khai producers phát metadata mới.
4. Theo dõi số message ở từng subscription theo version.
5. Sau khi consumers đã nâng và thời gian chuyển tiếp kết thúc, dọn rules cũ.

Không thay metadata âm thầm mà không có migration, vì lỗi routing thường **không xuất hiện dưới dạng HTTP 500** ở producer.

## 5. SQL filters: biểu thức điều kiện theo message properties

**SQL filter** sử dụng ngôn ngữ biểu thức kiểu SQL của Service Bus, **không phải SQL query chạy trực tiếp trên database**, không đọc JSON body và không hỗ trợ tất cả khả năng T-SQL của SQL Server.

Các ví dụ sau giả định publisher gửi application properties đúng như bảng mục 4.

| Mục tiêu | SQL filter mẫu | Ý nghĩa |
| --- | --- | --- |
| Tất cả order mới | `eventType = 'OrderCreated'` | Chọn đúng loại sự kiện |
| Order mới ở Việt Nam | `eventType = 'OrderCreated' AND region = 'VN'` | Cả hai điều kiện đúng |
| Order giá trị cao | `eventType = 'OrderCreated' AND amount >= 10000000` | So sánh số |
| Chọn hai thị trường | `region IN ('VN', 'TH')` | Region thuộc một tập |
| Ưu tiên cao hoặc đặc biệt | `priority >= 8 OR eventType = 'ManualReviewRequested'` | Một trong hai |
| Phân nhánh theo version | `schemaVer = 1 AND eventType = 'OrderCreated'` | Lọc contract v1 |
| Nhận tất cả | `1 = 1` hoặc rule true/filter phù hợp | Audit subscription |
| Loại tất cả | `1 = 0` hoặc false filter | Tạm không nhận, cần đánh giá dữ liệu đang chờ |

### 5.1. AND, OR và dấu ngoặc

Một rule sau:

~~~sql
eventType = 'OrderCreated'
AND region = 'VN'
AND amount >= 10000000
~~~

chọn **đơn hàng mới ở VN và giá trị cao**.

Một rule khác:

~~~sql
eventType = 'OrderCreated'
AND (region = 'VN' OR region = 'TH')
~~~

chọn đơn hàng mới ở VN hoặc TH. Dấu ngoặc giúp tránh hiểu sai thứ tự ưu tiên:

~~~sql
(eventType = 'OrderCreated' AND region = 'VN')
OR eventType = 'ManualReviewRequested'
~~~

**Không đồng nhất** biểu thức trên với:

~~~sql
eventType = 'OrderCreated'
AND (region = 'VN' OR eventType = 'ManualReviewRequested')
~~~

Hai biểu thức có tập message phù hợp khác nhau.

### 5.2. NULL, property thiếu và kiểu không phù hợp

Một message không có `region` không tự động tương đương `region = ''` hay `region = 'VN'`. Với SQL-like **three-valued logic**, so sánh liên quan tới property thiếu/NULL có thể dẫn tới trạng thái không TRUE, nên message không match rule mong muốn.

Ví dụ:

~~~text
message:
  eventType = "OrderCreated"
  region    = (missing)

filter:
  eventType = 'OrderCreated' AND region = 'VN'

expected:
  KHÔNG được chọn vào fulfillment-vn
~~~

Dùng **explicit required metadata validation tại publisher** thay vì giả định missing values sẽ được broker tự sửa. Các biểu thức kiểm tra NULL/exists phải được kiểm thử theo cú pháp và semantics được Service Bus hỗ trợ.

### 5.3. LIKE, IN và những điều cần tránh

Có thể dùng các biểu thức SQL filter như `LIKE` hoặc `IN` trong phạm vi được hỗ trợ. Nhưng:

- `LIKE` với wildcard dễ chọn quá rộng và tăng chi phí xử lý filter.
- Biểu thức quá dài làm khó kiểm toán và migration.
- Property names/values phải được chuẩn hóa, nhất là chữ hoa/thường và kiểu dữ liệu.
- Không lấy dữ liệu người dùng rồi ghép trực tiếp thành SQL rule expression mà không kiểm soát escaping/validation.
- Không dùng SQL filter như công cụ query toàn bộ message body hoặc làm phép tính nghiệp vụ nặng.

Nếu routing chỉ cần equality trên vài properties, đánh giá **correlation filter** thay vì SQL filter phức tạp.

## 6. Correlation filter: so khớp nhanh các trường chính xác

**Correlation filter** chọn message khi các system properties/application properties được chỉ định có **giá trị bằng nhau** theo mô hình hỗ trợ. Nếu cấu hình nhiều điều kiện, chúng kết hợp theo nghĩa **AND** trong cùng correlation rule.

Ví dụ điều kiện logic:

~~~text
eventType == "OrderCreated"
region    == "VN"
~~~

Phù hợp `fulfillment-vn` nếu chỉ cần event đúng loại và một vùng cố định.

### 6.1. SQL filter và Correlation filter khác gì?

| Khía cạnh | SQL filter | Correlation filter |
| --- | --- | --- |
| Kiểu biểu thức | Điều kiện SQL-like | Equality của các property được khai báo |
| `AND`/`OR` phức tạp | Có thể biểu đạt bằng expression | Không dùng một correlation filter để diễn đạt OR |
| So sánh lớn hơn/nhỏ hơn | Phù hợp, ví dụ `amount >= 10000000` | Không phải mục tiêu |
| Equality nhiều trường | Có | Có, thường thích hợp hơn |
| Dễ kiểm thử | Cần chú ý parser, kiểu, NULL, logic | Dễ đọc khi trường và giá trị rõ |
| Hiệu năng | Có chi phí đánh giá biểu thức | Thường tối ưu hơn cho matching equality |
| Trường hợp áp dụng | Fraud threshold, phân nhánh nhiều điều kiện | Event type + region + tenant |

### 6.2. Muốn OR với nhiều correlation filters?

Giả sử fulfillment muốn nhận đơn mới ở **VN hoặc TH**:

- Rule `vn-orders`: `eventType=OrderCreated` AND `region=VN`.
- Rule `th-orders`: `eventType=OrderCreated` AND `region=TH`.

Các rules của **cùng subscription** được xét theo logic **OR** ở mức chọn message. Đây là lý do quan trọng phải phân biệt điều kiện **AND trong một correlation filter** và **OR giữa các rules**.

Nếu muốn biểu thức duy nhất, SQL filter `eventType = 'OrderCreated' AND region IN ('VN','TH')` cũng diễn đạt cùng mục tiêu nghiệp vụ.

### 6.3. Trường hợp không nên dùng correlation filter

- Phải kiểm tra `amount >= 10000000`.
- Cần nhiều nhóm điều kiện OR lồng nhau trong **một biểu thức**.
- Muốn match pattern string.
- Cần logic phụ thuộc nhiều kiểu dữ liệu phức tạp.

Khi đó chọn SQL filter hoặc đơn giản hóa hợp đồng metadata tại producer trước.


## 7. Rule mặc định `$Default` và cách nhiều rules tương tác

### 7.1. `$Default` là gì?

Khi một subscription được tạo theo cách mặc định, Service Bus thường có rule tên **`$Default`** sử dụng bộ lọc **TRUE**. Điều này có nghĩa subscription có thể nhận **mọi message** của topic, không phụ thuộc metadata.

Ví dụ cấu hình chưa đúng:

~~~text
Topic orders.events
  Subscription fulfillment-vn
    $Default                 TRUE
    vn-orders                eventType='OrderCreated' AND region='VN'
~~~

Mong muốn: chỉ nhận OrderCreated/VN. Thực tế: rule `$Default` vẫn cho phép các message khác đi vào subscription.

**Bài học bắt buộc:** sau khi tạo custom rules, hãy **kiểm tra danh sách rules** và loại `$Default` nếu subscription chỉ được phép nhận message qua custom filters. Chỉ xóa `$Default` của **subscription đúng đích**, không xóa nhầm rule mặc định của `audit-all`.

### 7.2. Các rules được kết hợp theo logic OR ở mức chọn message

Giả sử subscription có hai rules:

~~~text
Rule A: region = 'VN'
Rule B: eventType = 'OrderCreated'
~~~

Message `region='VN', eventType='OrderCancelled'` khớp Rule A. Message `region='TH', eventType='OrderCreated'` khớp Rule B.

Vì vậy subscription có thể nhận **cả hai**, trong khi yêu cầu “OrderCreated **và** VN” cần:

~~~sql
eventType = 'OrderCreated' AND region = 'VN'
~~~

Đặt **hai rules độc lập** không tương đương điều kiện AND.

### 7.3. Nhiều rules chồng lấn và SQL actions

Giả sử:

~~~text
Rule A: eventType = 'OrderCreated'
Rule B: eventType = 'OrderCreated' AND region = 'VN'
~~~

Message OrderCreated/VN khớp cả hai. Khi có **rule actions** hoặc logic xử lý phụ thuộc số bản message, việc chồng lấn gây khó dự đoán kết quả và cần kiểm chứng theo semantics của phiên bản Service Bus/API đang dùng. Đừng thiết kế dựa vào giả định mọi trường hợp khớp nhiều rules sẽ chỉ sinh đúng một bản sao với cùng metadata.

Nguyên tắc vận hành:

- Tổ chức rules sao cho **không chồng lấn** khi mục tiêu nghiệp vụ là các luồng độc lập.
- Nếu cố ý có nhiều điều kiện bao phủ, viết tests cho cả số message nhận và property sau rule action.
- Bảo đảm **consumer idempotent** vì message redelivery cũng có thể xảy ra, ngay cả khi rules không chồng lấn.
- Dùng **mỗi subscription cho một mục đích nghiệp vụ rõ ràng**, thay vì dồn nhiều người tiêu thụ không liên quan vào một subscription.

### 7.4. Cách tạo rules an toàn

Khi cần chuyển từ nhận tất cả sang lọc có chọn lọc:

1. Xác nhận đúng namespace, topic, subscription và môi trường.
2. Ghi lại rule hiện có và mục tiêu expected routing.
3. Tạo custom rule với filter đã thử nghiệm.
4. Kiểm tra rule đã lưu và biểu thức đúng.
5. Chỉ sau đó **xóa `$Default`** nếu muốn subscription không nhận mọi message.
6. Gửi bộ message kiểm thử và kiểm tra counts.
7. Giám sát những event không còn đi vào subscription, nhất là trong giai đoạn chuyển đổi.

Nếu đang chuyển một hệ thống production có tải, nên cân nhắc **subscription mới + cutover** để dễ rollback thay vì sửa trực tiếp rule quan trọng trong giờ cao điểm.

## 8. Thiết kế ba subscriptions theo nghiệp vụ

Mục tiêu triển khai:

~~~text
Namespace: sb-orders-lab-<unique>
Topic:     orders.events

Subscriptions:
  fulfillment-vn:
    rule only-vn-new:
      eventType = 'OrderCreated' AND region = 'VN'

  fraud-review:
    rule high-value-new:
      eventType = 'OrderCreated' AND amount >= 10000000

  audit-all:
    rule $Default:
      TRUE
~~~

### 8.1. Vì sao tách thành ba subscription?

- Fulfillment xử lý giao hàng VN, có tốc độ xử lý, retry và dead-letter riêng.
- Fraud review kiểm tra đơn giá trị cao, có thể chậm hơn hoặc cần người duyệt.
- Audit phải nhận mọi event để ghi nhật ký nhưng không chặn fulfillment.
- Nếu Fraud service tạm dừng, backlog ở `fraud-review` tăng; `fulfillment-vn` vẫn có thể xử lý độc lập.
- Mỗi consumer có thể scale, quản lý quyền và theo dõi metrics riêng.

### 8.2. Bộ dữ liệu kiểm thử có kết quả xác định

| Event | `eventType` | `region` | `amount` | Fulfillment VN | Fraud | Audit |
| --- | --- | --- | ---: | :---: | :---: | :---: |
| E1 | OrderCreated | VN | 12.500.000 | Có | Có | Có |
| E2 | OrderCreated | TH | 2.000.000 | Không | Không | Có |
| E3 | OrderCreated | VN | 900.000 | Có | Không | Có |
| E4 | OrderCancelled | VN | 15.000.000 | Không | Không | Có |
| E5 | OrderCreated | *(thiếu)* | 20.000.000 | Không | Có | Có |
| E6 | PaymentCaptured | SG | 50.000.000 | Không | Không | Có |

**Kết quả dự kiến với 6 events hợp lệ:**

~~~text
fulfillment-vn = 2 messages  (E1, E3)
fraud-review   = 2 messages  (E1, E5)
audit-all      = 6 messages  (E1, E2, E3, E4, E5, E6)
~~~

E1 có trong **ba subscriptions** là đúng. E5 không có `region` nhưng vẫn khớp fraud rule vì fraud rule chỉ yêu cầu `eventType` và `amount`.

### 8.3. Trường hợp test âm tính (negative tests)

Đừng chỉ gửi event “đúng chuẩn”. Cần kiểm tra:

| Input sai hoặc bất thường | Rủi ro |
| --- | --- |
| `amount="12500000"` dưới dạng string | SQL numeric comparison có thể không match hoặc evaluation error |
| Không có `eventType` | Các subscriptions chọn theo loại event không nhận |
| `eventType="ordercreated"` thay vì `OrderCreated` | Có thể làm routing sai khi không tuân hợp đồng casing |
| `region="V N"` hoặc `region="Vietnam"` | Metadata không chuẩn hóa nên không match `VN` |
| `amount` là số âm hoặc vượt giới hạn business | Consumer nhận dữ liệu vô nghĩa nếu không validate |
| Message body hợp lệ nhưng metadata thiếu | Bộ lọc không tự đọc body |
| Message đến đúng topic nhưng subscription đã tắt hoặc auto-forward | Receiver đọc không đúng endpoint |

Các tests nên ghi rõ **expected match, expected non-match và expected error handling**. Nếu metadata malformed, producer nên từ chối trước khi publish thay vì trông chờ broker đánh giá lỗi.

## 9. Tạo resources và rules qua Azure portal

### 9.1. Điều kiện trước khi làm

- Azure subscription/namespace được phép sử dụng và có đủ quyền.
- Namespace Service Bus thuộc tier **Standard hoặc Premium** để dùng topic/subscriptions.
- Tên namespace duy nhất, region theo yêu cầu dữ liệu và chính sách.
- Billing, Azure RBAC và cơ chế authentication đã được phê duyệt.
- Một topic `orders.events` hoặc tên khác theo quy tắc hợp lệ.
- Tài khoản có quyền **quản lý rule** và thực hiện **send/receive test messages** nếu thực hành.

Không tạo resource hoặc sửa rules ở production trước khi có quy trình thay đổi, kế hoạch kiểm thử và rollback. **Tạo namespace/tier Premium có thể phát sinh phí đáng kể**; cân nhắc lab Standard nếu tính năng yêu cầu được hỗ trợ.

### 9.2. Tạo Topic

Trong Azure portal:

1. Chọn đúng subscription/resource group rồi mở **Service Bus namespace**.
2. Xác nhận namespace tier có hỗ trợ topic.
3. Trong mục **Topics**, tạo `orders.events`.
4. Chọn TTL, duplicate detection, partitioning hoặc các thuộc tính khác theo nhu cầu **và điều kiện tier**. Không bật tùy chọn chỉ vì thấy nó xuất hiện mà chưa hiểu tác động.
5. Kiểm tra topic đã được tạo, trạng thái hoạt động và quyền publisher.

### 9.3. Tạo Fulfillment subscription

1. Trong topic `orders.events`, tạo subscription `fulfillment-vn`.
2. Kiểm tra lock duration, max delivery count, TTL và DLQ policy tùy tiêu chuẩn của đội.
3. Mở mục **Rules / Filters** của subscription.
4. Tạo rule tên `only-vn-new` thuộc loại **SQL filter**:

~~~sql
eventType = 'OrderCreated' AND region = 'VN'
~~~

5. Xác minh biểu thức hiển thị đúng sau khi lưu.
6. **Xóa rule `$Default`** nếu nó tồn tại và đang để TRUE.
7. Kiểm tra chỉ còn rule cần thiết.

Một cách thay thế là tạo subscription với custom rule ngay bằng API/SDK có hỗ trợ; khi đó vẫn cần kiểm tra bộ rules thực tế để không giả định `$Default` đã biến mất.

### 9.4. Tạo Fraud subscription

Tạo `fraud-review` với custom SQL rule `high-value-new`:

~~~sql
eventType = 'OrderCreated' AND amount >= 10000000
~~~

Sau khi tạo, kiểm tra và xóa `$Default` nếu subscription cần **chỉ nhận high-value OrderCreated**.

### 9.5. Tạo Audit subscription

Tạo `audit-all` và **giữ rule `$Default` (True)** nếu thực sự muốn audit tất cả events của topic.

Khi muốn audit chỉ một số event family, dùng custom rule, nhưng phải thay đổi bảng kỳ vọng và đặt chính sách riêng. Audit data có thể chứa thông tin nhạy cảm; quyền truy cập, retention và log phải phù hợp quy định dữ liệu.

### 9.6. Xác minh trước khi publish

| Subscription | Bộ rules mong đợi | `$Default` |
| --- | --- | --- |
| `fulfillment-vn` | `only-vn-new` | **Không có** |
| `fraud-review` | `high-value-new` | **Không có** |
| `audit-all` | `$Default` | **Có, TRUE** |

Hãy chụp/ghi cấu hình rule expressions và môi trường thử nghiệm theo quy trình nội bộ, không ghi secrets/connection strings vào ảnh minh họa.

## 10. Quản lý rules bằng Azure CLI và API/SDK

### 10.1. Xác minh subscription trước khi thay đổi

Ví dụ Azure CLI ở chế độ chỉ đọc:

~~~bash
az login
az account show \
  --query "{name:name, subscriptionId:id, tenantId:tenantId}" \
  --output json

# Chọn đúng subscription đã được phân công.
az account set --subscription "<SUBSCRIPTION_ID>"

RG="rg-messaging-lab"
SBNS="sb-orders-lab-unique"
TOPIC="orders.events"

# Danh sách subscriptions và rules của một subscription.
az servicebus topic subscription list \
  --resource-group "$RG" \
  --namespace-name "$SBNS" \
  --topic-name "$TOPIC" \
  --output table

az servicebus topic subscription rule list \
  --resource-group "$RG" \
  --namespace-name "$SBNS" \
  --topic-name "$TOPIC" \
  --subscription-name fulfillment-vn \
  --output json
~~~

Các lệnh `list` là đọc cấu hình, không tiêu thụ message. Cú pháp quản trị rules và filter-type có thể khác theo Azure CLI version; dùng `az servicebus topic subscription rule --help` trước khi thực hiện create/delete.

### 10.2. Tạo rule bằng CLI (chỉ chạy trong lab được phép)

Ví dụ cấu trúc lệnh cho một CLI có hỗ trợ SQL expression parameter:

~~~bash
az servicebus topic subscription rule create \
  --resource-group "$RG" \
  --namespace-name "$SBNS" \
  --topic-name "$TOPIC" \
  --subscription-name fulfillment-vn \
  --name only-vn-new \
  --filter-sql-expression "eventType = 'OrderCreated' AND region = 'VN'"
~~~

**Đây là thao tác ghi cấu hình.** Kiểm tra help/schema của phiên bản Azure CLI hiện cài và filter type mặc định trước khi chạy, bởi syntax có thể có thêm các yêu cầu hoặc thay đổi. Nếu command báo unrecognized argument, **không cố sửa ngẫu nhiên trên production**; dùng portal hoặc SDK/ARM API có cấu hình rõ ràng.

Sau khi tạo, đọc lại:

~~~bash
az servicebus topic subscription rule list \
  --resource-group "$RG" \
  --namespace-name "$SBNS" \
  --topic-name "$TOPIC" \
  --subscription-name fulfillment-vn \
  --output json
~~~

Chỉ xóa `$Default` khi đã xác minh custom filter đúng, có phép rollback và quyền:

~~~bash
az servicebus topic subscription rule delete \
  --resource-group "$RG" \
  --namespace-name "$SBNS" \
  --topic-name "$TOPIC" \
  --subscription-name fulfillment-vn \
  --name '$Default'
~~~

**Cảnh báo quoting:** trong Bash, `'$Default'` là literal; dùng `"$Default"` có thể bị shell thay biến và xóa sai/không được gì. PowerShell cũng có quy tắc quoting riêng; dùng literal đúng cho shell đang chạy.

Lặp lại tương tự cho fraud subscription. **Không xóa `$Default` ở audit-all.**

### 10.3. Ví dụ .NET Administration SDK cho SQL rule

Một ứng dụng quản trị rule có thể dùng package `Azure.Messaging.ServiceBus` và `Azure.Identity`:

~~~csharp
using Azure.Identity;
using Azure.Messaging.ServiceBus.Administration;

string fullyQualifiedNamespace = "sb-orders-lab-unique.servicebus.windows.net";
string topic = "orders.events";
string subscription = "fulfillment-vn";

var admin = new ServiceBusAdministrationClient(
    fullyQualifiedNamespace,
    new DefaultAzureCredential());

var filter = new SqlRuleFilter(
    "eventType = 'OrderCreated' AND region = 'VN'");

var rule = new CreateRuleOptions("only-vn-new", filter);

// Chỉ tạo khi rule chưa tồn tại, trong môi trường được phép.
await admin.CreateRuleAsync(topic, subscription, rule);

// Kiểm tra tất cả rules trước khi xóa $Default.
await foreach (RuleProperties item in admin.GetRulesAsync(topic, subscription))
{
    Console.WriteLine($"Rule: {item.Name}");
}

// Sau khi xác minh cấu hình và quyền, có thể xóa rule mặc định.
// await admin.DeleteRuleAsync(topic, subscription, "$Default");
~~~

**Điều kiện:** subscription đã tồn tại, danh tính quản trị có quyền phù hợp đối với quản lý entities/rules, SDK/API tương thích và mạng truy cập namespace cho phép. Lệnh create không idempotent nếu tên rule đã có; xử lý conflict và quy trình change management trong code thực.

### 10.4. Ví dụ .NET Correlation rule

Với routing `eventType` + `region` bằng equality:

~~~csharp
var correlation = new CorrelationRuleFilter();
correlation.ApplicationProperties["eventType"] = "OrderCreated";
correlation.ApplicationProperties["region"] = "VN";

var rule = new CreateRuleOptions("only-vn-correlation", correlation);

// ĐÂY LÀ PHƯƠNG ÁN THAY THẾ SQL RULE, không tạo cả hai
// trừ khi bạn đã kiểm chứng chồng lấn rules.
// await admin.CreateRuleAsync(topic, subscription, rule);
~~~

Ví dụ này thay thế rule SQL ở Fulfillment, không nên thêm song song vào production khi chưa kiểm thử. Khi tạo correlation rule cho system properties, phải dùng đúng các trường của SDK như `CorrelationId`, `Subject` theo API hỗ trợ, tránh tự viết tên property tùy tiện.

### 10.5. Quản lý cấu hình bằng IaC

Với production, lưu names, filter expressions, subscription settings và ownership trong **Bicep/ARM/Terraform hoặc công cụ IaC** phù hợp. Nguyên tắc:

- Review mỗi lần đổi expression.
- Lưu version/rollback history.
- Deploy có kiểm soát sang Dev → Staging → Prod.
- Dùng desired-state reconciliation có cảnh báo khi resource khác với cấu hình dự kiến.
- Không để cả portal và pipeline tự ý chỉnh rules mà không có quy trình chung.
- Quan sát backlog cũ trong lúc thay đổi rules; đừng chỉ đổi IaC rồi kết luận message đã di chuyển.

## 11. Gửi message và xem kết quả bằng Python SDK

### 11.1. Điều kiện

- `pip install azure-servicebus azure-identity` trong **môi trường lab riêng**.
- Namespace đã có topic, subscriptions, rules đúng.
- Identity dùng để gửi có quyền `Azure Service Bus Data Sender` hoặc data-plane quyền tương ứng.
- Identity dùng để nhận có `Azure Service Bus Data Receiver` tương ứng với từng subscription.
- Mạng và endpoint Service Bus cho phép kết nối; cấu hình TLS/network theo chính sách.
- Message bodies trong ví dụ chỉ chứa **dữ liệu giả**.

Không dùng namespace production để chạy ví dụ nếu chưa được phê duyệt, và không gửi PII/credential vào message test.

### 11.2. Publisher: body JSON và metadata có kiểu

~~~python
import json
import os
from azure.identity import DefaultAzureCredential
from azure.servicebus import ServiceBusClient, ServiceBusMessage

namespace = os.environ["SERVICEBUS_NAMESPACE"]
topic = "orders.events"

test_events = [
    ("E1", "OrderCreated", "VN", 12500000),
    ("E2", "OrderCreated", "TH", 2000000),
    ("E3", "OrderCreated", "VN", 900000),
    ("E4", "OrderCancelled", "VN", 15000000),
    ("E5", "OrderCreated", None, 20000000),
    ("E6", "PaymentCaptured", "SG", 50000000),
]

credential = DefaultAzureCredential()

with ServiceBusClient(
    fully_qualified_namespace=namespace,
    credential=credential,
) as client:
    with client.get_topic_sender(topic_name=topic) as sender:
        for event_id, event_type, region, amount in test_events:
            properties = {
                "eventType": event_type,
                "amount": amount,  # integer, không phải chuỗi
                "schemaVer": 1,
            }
            if region is not None:
                properties["region"] = region

            payload = {
                "eventId": event_id,
                "orderId": f"TEST-{event_id}",
                "amount": amount,
            }

            message = ServiceBusMessage(
                body=json.dumps(payload),
                message_id=f"lesson-004-{event_id}",
                correlation_id=f"lab-batch-{event_id}",
                subject=event_type,
                content_type="application/json",
                application_properties=properties,
            )
            sender.send_messages(message)
            print("Published:", event_id)
~~~

Ví dụ dùng **Microsoft Entra ID** qua `DefaultAzureCredential`, không lưu SAS connection string trong mã. Biến môi trường `SERVICEBUS_NAMESPACE` chứa **fully qualified namespace**, ví dụ `sb-orders-lab-unique.servicebus.windows.net`.

**Lưu ý duplicate detection:** nếu namespace/topic bật duplicate detection và bạn gửi lại cùng `message_id` trong detection window, một số messages có thể bị broker loại như duplicate. Để kiểm thử nhiều lần, dùng **lab batch identifier mới** trong message IDs và ghi lại batch đó, hoặc dọn/reset có kiểm soát. Đừng tắt duplicate detection trong production chỉ để chạy test.

### 11.3. Receiver của một subscription

~~~python
import os
from azure.identity import DefaultAzureCredential
from azure.servicebus import ServiceBusClient

namespace = os.environ["SERVICEBUS_NAMESPACE"]
topic = "orders.events"
subscription = "fulfillment-vn"

with ServiceBusClient(
    fully_qualified_namespace=namespace,
    credential=DefaultAzureCredential(),
) as client:
    with client.get_subscription_receiver(
        topic_name=topic,
        subscription_name=subscription,
        max_wait_time=5,
    ) as receiver:
        messages = receiver.receive_messages(
            max_message_count=20,
            max_wait_time=5,
        )

        for message in messages:
            print("MessageId:", message.message_id)
            print("Properties:", message.application_properties)
            print("Body:", str(message))
            # Trong bài lab, complete sau khi đã kiểm chứng nội dung.
            receiver.complete_message(message)
~~~

Đây là **receiver tiêu thụ thật**: gọi `complete_message` sẽ loại message khỏi subscription sau khi xử lý. Nếu chỉ muốn xem mà **không tiêu thụ**, dùng **Service Bus Explorer Peek** trong portal hoặc `peek_messages` trong SDK.

Không chạy receiver tiêu thụ trên subscription production để kiểm thử bộ lọc. Nếu `receive_messages` trả danh sách trống, có thể do subscription đã được consumer khác xử lý, filter không match, entity sai, chưa có message hoặc quyền/network, không nhất thiết do SDK hỏng.

### 11.4. Xác minh đủ ba subscriptions

Gửi batch vào một **namespace/topic test sạch**, không có traffic khác. Sau khi gửi, dùng peek hoặc receiver lab theo thứ tự:

~~~text
fulfillment-vn: E1, E3
fraud-review:   E1, E5
audit-all:      E1, E2, E3, E4, E5, E6
~~~

Khi không khớp:

1. Kiểm tra `$Default` của từng subscription.
2. Kiểm tra SQL/correlation rules đã được lưu.
3. Kiểm tra tên/kiểu application properties của message nhận.
4. Kiểm tra duplicate detection và message IDs.
5. Kiểm tra TTL, auto-forwarding, DLQ, consumer đã chạy hay chưa.
6. Kiểm tra publish time so với thời điểm rule có hiệu lực.

**Không kết luận sai filter chỉ từ queue count** trên môi trường có consumers đang xử lý hoặc messages cũ.


## 12. Những mẫu định tuyến nâng cao

### 12.1. Fan-out theo trách nhiệm và lọc theo sự kiện

Một topic `business.events` có thể phục vụ:

~~~text
business.events
  ├── billing-sub         eventType IN ('InvoiceCreated', 'InvoicePaid')
  ├── shipping-sub        eventType = 'OrderReadyToShip'
  ├── notifications-sub   eventType IN ('OrderCreated', 'OrderDelivered')
  └── audit-sub           TRUE
~~~

**Ưu điểm:** publisher chỉ biết event contract và topic. Khi nhóm notifications thay đổi, publisher không phải gọi thêm endpoint riêng.

**Nhược điểm:** cần quản lý metadata schema và route ownership; các consumers không được giả định message từ mọi subscription có cùng payload.

### 12.2. Định tuyến theo tenant

Một hệ thống đa khách hàng có thể dùng property `tenantKey`:

~~~sql
eventType = 'UsageReported' AND tenantKey = 'tenant-02'
~~~

Nhưng **filter không phải ranh giới bảo mật thay cho RBAC**. Nếu một principal được cấp quyền Receive trên subscription chứa dữ liệu tenant khác, filter sai có thể khiến dữ liệu chảy tới consumer không được phép.

Khi cần cách ly nghiêm ngặt:

- Chia namespaces/topics/subscriptions theo mức trust boundary phù hợp.
- Cấp role/scope tối thiểu.
- Mã hóa và giảm thông tin nhạy cảm trong message.
- Kiểm soát rule changes qua review/IaC.
- Có tests bảo đảm **không cross-tenant delivery**.

Không mặc định “mỗi tenant một subscription” là cấu trúc tối ưu nếu số tenant rất lớn; cần xem quota, chi phí quản trị, ownership và băng thông.

### 12.3. Định tuyến theo phiên bản schema

Giả sử producer đang chuyển từ `eventType='OrderCreated'` và `schemaVer=1` sang version 2.

Có thể tạo rule chuyển tiếp:

~~~sql
eventType = 'OrderCreated'
AND (schemaVer = 1 OR schemaVer = 2)
~~~

Hoặc hai subscriptions/rules dành cho các consumers hỗ trợ version khác nhau. Quan trọng là:

1. Producer, filter và consumer đều thống nhất version.
2. Chỉ loại bỏ version cũ sau khi dữ liệu cũ/backlog đã được xử lý.
3. Không thay đổi ý nghĩa của property hiện có mà không đánh dấu version.
4. Có contract tests kiểm tra body và metadata đi cùng nhau.

### 12.4. Định tuyến ưu tiên

Có thể dùng hai subscriptions:

~~~text
priority-review:
  eventType = 'OrderCreated' AND priority >= 8

standard-fulfillment:
  eventType = 'OrderCreated' AND priority < 8
~~~

Trong ví dụ, rules **không chồng lấn** với message có numeric `priority` hợp lệ. Nếu `priority` thiếu hoặc sai kiểu, message có thể không match cả hai.

**Lưu ý:** hai subscriptions này là hai luồng độc lập, không tự tạo ra một queue có “ưu tiên xử lý” tuyệt đối. Consumer scheduling, scaling và downstream phải được thiết kế riêng. Nếu tất cả đơn hàng vẫn phải đi fulfillment, dùng một subscription fulfillment-all và một subscription priority-review sẽ hợp lý hơn.

### 12.5. Định tuyến theo system properties

Correlation filters có thể so sánh các system properties được SDK hỗ trợ như `CorrelationId`, `Subject` hoặc `SessionId` trong phạm vi tương ứng. SQL filter cũng có thể tham chiếu **system properties qua cú pháp dành riêng** của Service Bus, khác với việc đọc application properties.

Không tự giả định tên property trong SQL expression luôn giống thuộc tính .NET/Python SDK hiển thị. Ví dụ `Subject` ở SDK có thể tương ứng cách đặt tên lịch sử `Label` trong một số API/filter contexts. Hãy chọn **một quy ước và kiểm thử thực tế** thay vì sao chép tên property từ SDK vào SQL filter một cách máy móc.

### 12.6. Auto-forwarding từ subscription sang queue/topic khác

Một subscription có thể cấu hình **auto-forwarding** tới entity Service Bus được hỗ trợ, thường trong **cùng namespace**:

~~~mermaid
flowchart LR
    P["Producer"]
    T["Topic orders.events"]
    S["Subscription high-value"]
    Q["Queue manual-review"]
    W["Review worker"]
    P --> T -->|"filter amount >= threshold"| S
    S -->|"auto-forward"| Q --> W
~~~

Lợi ích:

- Broker tự chuyển message phù hợp sang queue mà consumer cần.
- Có thể tách subscriber routing khỏi hàng đợi xử lý riêng.
- Producer vẫn không cần biết queue cuối cùng.

Điều cần kiểm tra:

- Forwarding chỉ xảy ra với message đã **vào subscription**; filter sai không được auto-forward “cứu”.
- Target phải tồn tại, hỗ trợ tính năng và đủ quyền/năng lực.
- Có giới hạn/điều kiện đối với forwarding chains.
- Delivery count, TTL, transfer dead-letter và error handling phải được giám sát.
- Không tạo vòng lặp tự chuyển tiếp hoặc chuỗi khó kiểm soát.
- Nếu forwarding được bật, **message có thể không còn nằm ở subscription nguồn để receiver đọc như trước**, tùy cấu hình.

Không tự tạo rules tương ứng ở target rồi giả định broker sẽ xử lý định tuyến theo cách giống một topic khác; phải xem loại entity đích và consumer semantics.

### 12.7. SQL rule actions thay đổi metadata, không thay body nghiệp vụ

Một SQL rule action có thể được dùng để **biến đổi các message properties được hỗ trợ** của message phù hợp trước khi đưa tới subscription, chẳng hạn gắn nhãn route/phân loại.

Ví dụ ý tưởng:

~~~text
Filter:
  eventType = 'OrderCreated' AND amount >= 10000000

Action (mô tả nghiệp vụ):
  gắn property routeCategory = "high-value-review"
~~~

Đây là **mô tả hành vi**, không phải cú pháp SQL action có thể deploy nguyên văn. Khi triển khai cần dùng cú pháp và giới hạn property của **Service Bus SQL action** trong API/SDK tương ứng.

Tránh dùng action để:

- Thay đổi body JSON hoặc schema mà không có hợp đồng consumer.
- Giả định tác động vào bản message gốc trong topic hoặc các subscriptions khác.
- Thực hiện nghiệp vụ nặng như gọi database/API (broker filter/action không chạy arbitrary business code).
- Sửa các system properties không được phép hoặc nhúng logic nhạy cảm khó kiểm toán.

Nếu nhiều overlapping rules có actions, cần kiểm thử **số bản message, properties và thứ tự áp dụng** đúng theo semantics của dịch vụ. Phương án rõ ràng hơn thường là tách subscriptions hoặc làm giàu metadata ngay tại producer.

## 13. Dead-letter, TTL, duplicate detection và sessions

### 13.1. Không match filter khác dead-letter

| Trường hợp | Kết quả ở subscription |
| --- | --- |
| Message không match bất cứ rule nào | Không được chọn đưa vào subscription |
| Message match, consumer xử lý thành công | Có thể được `Complete` và loại khỏi subscription |
| Message match, consumer liên tục lỗi | Có thể bị retry, sau đó DLQ theo max delivery/policy |
| Message hết TTL | Có thể bị xóa/đưa DLQ tùy chính sách cấu hình và khả năng |
| Filter evaluation exception | Xem dead-letter-on-filter-evaluation-exceptions và hành vi cụ thể của entity |
| Auto-forwarding lỗi | Có thể cần điều tra transfer DLQ và target state |
| Duplicate detection tại topic | Publisher có thể không nhìn thấy một bản message độc lập trong subscription nếu broker loại duplicate |

**Không dùng DLQ để thống kê tất cả message bị bộ lọc loại.** DLQ chỉ phản ánh những tình trạng được broker/receiver dead-letter theo cơ chế hỗ trợ.

### 13.2. Các thao tác settlement với PeekLock

Trong chế độ `PeekLock`, receiver có thể:

- `Complete`: xác nhận đã xử lý xong.
- `Abandon`: trả message để có thể nhận lại.
- `DeadLetter`: chuyển message lỗi có chủ đích vào DLQ.
- `Defer`: hoãn message để xử lý theo sequence number/cơ chế phù hợp.
- Không hoàn tất trước khi lock hết hạn: message có thể được nhận lại.

**Định tuyến vào subscription** xảy ra trước những thao tác này. Consumer không thể “sửa SQL filter” bằng cách Complete hay Abandon message đã nhận.

### 13.3. Consumer phải idempotent

Giả sử message E1 đã vào `fraud-review`. Worker ghi trạng thái kiểm tra thành công nhưng crash trước `Complete`. Sau lock timeout, message có thể được giao lại.

Cần:

1. Tạo idempotency key từ business event ID/`MessageId` theo contract.
2. Ghi trạng thái xử lý vào store bền vững.
3. Chỉ thực hiện side effects một lần về mặt nghiệp vụ.
4. Ghi error codes/trace IDs để điều tra.
5. Có poison/DLQ runbook và quyền xử lý riêng.

SQL filter không đảm bảo exactly-once processing của consumer.

### 13.4. Duplicate detection khác idempotency

Service Bus có khả năng **duplicate detection** theo MessageId và khoảng thời gian cấu hình ở những tier/entity hỗ trợ. Tính năng này có thể giúp giảm message trùng tại broker, nhưng:

- Không giải quyết consumer redelivery sau khi nhận.
- Không bảo vệ nghiệp vụ nếu cùng đơn được gửi với hai message IDs khác nhau.
- Có window/quota/throughput trade-offs.
- Cần hiểu tương tác với partitioning và session settings theo entity.

Giữ **idempotency ở consumer** dù broker có duplicate detection.

### 13.5. Sessions và thứ tự xử lý

Nếu cần xử lý message của một đơn theo thứ tự:

~~~text
OrderCreated  (SessionId = ORD-1001)
OrderPaid     (SessionId = ORD-1001)
OrderShipped  (SessionId = ORD-1001)
~~~

Service Bus **sessions** có thể giúp tổ chức thứ tự và khóa xử lý **trong một session** khi entity và receiver được cấu hình phù hợp. Tuy nhiên:

- Không có tổng thứ tự toàn topic across subscriptions.
- Mỗi subscription có tiến độ nhận độc lập.
- Filters phải được thiết kế để không làm mất một event cần thiết trong chuỗi state machine.
- Session-enabled subscription yêu cầu session-aware receiver.
- Không dùng `CorrelationId` thay cho `SessionId` rồi kỳ vọng session lock hoạt động.

### 13.6. TTL và backlog khi sửa filter

Message đã ở subscription có thể tiếp tục tồn tại đến khi được xử lý/hết TTL theo chính sách. Xóa rule không tự xóa backlog cũ.

Nếu áp dụng filter mới `region = 'VN'` ở t=10:00, message non-VN đã được chọn vào subscription trước 10:00 có thể **vẫn hiện trong backlog**. Khi thử nghiệm, dùng **batch IDs và mốc publish time** để tránh nhầm.

## 14. Bảo mật: quyền publish, nhận và quản lý rules

### 14.1. Phân biệt ba nhóm quyền

| Nhóm | Công việc | Quyền cần |
| --- | --- | --- |
| Publisher | Gửi message vào topic | Data-plane `Azure Service Bus Data Sender` hoặc quyền tương đương |
| Consumer | Receive/Complete/DeadLetter trong subscription | `Azure Service Bus Data Receiver` hoặc quyền tương đương |
| Administrator/IaC | Tạo topic, subscription, rules; đổi filters | Quyền management-plane/rule management phù hợp scope, hoặc API admin role có khả năng tương ứng |

**Quyền Send không đồng nghĩa quyền sửa rules.** Quyền Receive của một subscription không nên được mở rộng thành quyền xem mọi subscription khác nếu không cần.

### 14.2. Managed identity trước khi dùng SAS connection strings

Trên Azure VM, App Service, Functions, AKS hoặc Container Apps, ưu tiên managed identity với RBAC đúng scope khi SDK hỗ trợ. Lợi ích:

- Không đưa namespace key vào code.
- Có thể thu hồi/thay quyền theo identity.
- Phân biệt publisher, fraud worker và audit worker.

Khi dùng SAS, tránh `RootManageSharedAccessKey` có quyền rộng cho một consumer đơn lẻ. Bảo vệ secret trong Key Vault và có kế hoạch rotation.

### 14.3. Network security là tầng riêng

Một client có role hợp lệ vẫn có thể không kết nối được khi:

- Namespace firewall chặn egress IP.
- Private Endpoint/Private DNS cấu hình sai.
- VNet routing/NSG chặn port/protocol.
- TLS hostname hoặc chứng chỉ không hợp lệ.

RBAC và network routing phải được kiểm tra độc lập. Không hạ mức bảo mật mạng khi lỗi thực sự do filter expression.

### 14.4. Metadata có thể tiết lộ thông tin

Không đặt số thẻ thanh toán, mật khẩu, access token hoặc thông tin cá nhân không cần thiết vào `application_properties` chỉ để filter. Broker cần metadata đủ để định tuyến, **không cần biết toàn bộ dữ liệu nghiệp vụ**.

Nếu cần route theo giá trị đơn hàng, cân nhắc property `isHighValue` hoặc `amountBucket` với hợp đồng rõ, thay vì gửi dữ liệu nhạy cảm/có độ chính xác cao không cần thiết.

### 14.5. Filter là chính sách nghiệp vụ nhưng không phải authorization

Một subscription đặt rule `tenantKey='A'` không đủ để coi dữ liệu đã được cách ly tuyệt đối. Phải kiểm soát:

- Ai sửa được rule?
- Ai gửi message với `tenantKey` giả mạo?
- Ai có quyền Receive trên subscription?
- Ai có thể bật thêm `$Default` hoặc thêm rule TRUE?
- Có policy, review và audit log đối với thay đổi filter không?

Publisher phải xác thực và hệ thống cần validate metadata từ nguồn được tin cậy, thay vì chấp nhận `tenantKey` do client public tùy ý gửi.


## 15. Observability: theo dõi routing và health của subscriptions

### 15.1. Các nhóm metric và tín hiệu

Khi triển khai filter/rule, đừng chỉ xem publisher có gọi `send` thành công không. Cần quan sát theo **topic và từng subscription**.

| Tín hiệu | Điều cần xác minh |
| --- | --- |
| Incoming messages tại topic | Publisher thật sự đã gửi bao nhiêu message |
| Active messages ở từng subscription | Message đã được chọn nhưng chưa xử lý |
| Outgoing/completed messages | Consumer có xử lý/settle được không |
| Dead-lettered messages | Message processing/filter/forwarding có lỗi không |
| Scheduled/transfer messages khi áp dụng | Có message chờ hoặc auto-forwarding issues không |
| Server errors/user errors/throttling | Broker hoặc client đang gặp lỗi gì |
| Consumer success/failure và latency | Message hợp lệ nhưng processing có chậm không |
| SQL filter/rule inventory | Có bị thêm `$Default`, rule TRUE, rule chồng lấn không |
| Application trace IDs | Có theo dõi được từ producer tới từng consumer không |
| Cost/throughput/capacity | Filter phức tạp hoặc fan-out nhiều có tạo thêm tải không |

Metric names, entity dimensions và khả năng hiển thị có thể khác giữa Azure Monitor resource types/tier. Trước khi dựng dashboard, kiểm tra metric definitions đang có của namespace/từng entity.

### 15.2. Phân biệt broker metrics và application logs

Một topic có 1.000 incoming messages, nhưng ba subscriptions có tổng 2.200 messages phù hợp là chuyện bình thường: **fan-out làm tổng messages ở subscriptions lớn hơn số publish**.

Tuy nhiên, nếu `fulfillment-vn` bất ngờ tăng gấp đôi sau khi thêm rule, phải kiểm tra:

1. Có vô tình giữ `$Default` không?
2. Có thêm overlapping rule/action không?
3. Consumer có retry khiến logs đếm invocation thay vì unique MessageId không?
4. Publisher có gửi message trùng không?
5. Dashboard đang đếm active, completed, incoming hay toàn bộ traffic?

**Không lấy “3 subscribers” để suy ra luôn đúng 3 message bản sao với mọi event**; chỉ các subscriptions có rules phù hợp mới nhận.

### 15.3. Kiểm tra rules bằng CLI

Các lệnh chỉ đọc:

~~~bash
az servicebus topic subscription rule list \
  --resource-group "$RG" \
  --namespace-name "$SBNS" \
  --topic-name "$TOPIC" \
  --subscription-name fulfillment-vn \
  --output json

az servicebus topic subscription rule list \
  --resource-group "$RG" \
  --namespace-name "$SBNS" \
  --topic-name "$TOPIC" \
  --subscription-name fraud-review \
  --output json

az servicebus topic subscription rule list \
  --resource-group "$RG" \
  --namespace-name "$SBNS" \
  --topic-name "$TOPIC" \
  --subscription-name audit-all \
  --output json
~~~

Trong quy trình production, nên có automation kiểm tra “rules đang áp dụng” so với IaC source of truth. Các lệnh này không thay thế kiểm thử bằng message thật.

### 15.4. Azure Monitor và Application Insights

Có thể thu telemetry từ publisher/consumer với các trường sau:

~~~json
{
  "service": "fraud-worker",
  "topic": "orders.events",
  "subscription": "fraud-review",
  "eventId": "E1",
  "messageId": "lesson-004-E1",
  "correlationId": "lab-batch-E1",
  "eventType": "OrderCreated",
  "result": "processed",
  "durationMs": 120
}
~~~

Không đưa full message body nếu chứa thông tin nhạy cảm. Với Application Insights, nên gắn trace context/correlation ID xuyên suốt việc publish–receive. Không mặc định transport tự tạo distributed trace đầy đủ khi producer và consumer dùng hai SDK/runtime khác nhau.

### 15.5. Đọc counts có bối cảnh

Để kiểm thử filter:

- Dùng **topic/subscriptions lab riêng**, consumer khác tắt hoặc được phối hợp.
- Ghi lại `MessageId`, batch ID, thời gian publish.
- Peek từng subscription trước khi `Complete`.
- So sánh **tập IDs** chứ không chỉ một con số tổng.
- Ghi trạng thái backlog trước và sau test.
- Đánh giá TTL, duplicate detection, auto-forwarding và sessions.

Nếu chạy cả producers và consumers production, ActiveMessageCount có thể gần 0 ngay cả khi routing hoạt động đúng do consumers xử lý quá nhanh.

## 16. Hiệu năng, độ phức tạp và chi phí của filter

### 16.1. SQL filter phức tạp có chi phí xử lý

Một rule càng phức tạp, càng nhiều subscriptions/rules cần xét, workload broker càng có thể phải làm nhiều việc. Điều này ảnh hưởng throughput/latency theo tier và tải thực tế.

**Nguyên tắc tối ưu:**

- Với các phép equality đơn giản, đánh giá correlation filter.
- Dùng metadata ngắn, có kiểu rõ và được chuẩn hóa.
- Tránh hàng trăm biểu thức `OR`/`LIKE` dài nếu có thể tái thiết kế event taxonomy.
- Không gửi cả JSON body vào một string property rồi dùng filter pattern matching.
- Giảm số rules chồng lấn và dọn rules không còn chủ sở hữu.
- Kiểm thử latency và throughput theo **tải dự kiến**, không chỉ vài messages.

### 16.2. Fan-out có chi phí tài nguyên

Nếu publisher gửi 1 triệu events/ngày và mỗi event khớp trung bình 2,5 subscriptions, broker/consumers phải xử lý khoảng 2,5 triệu **message deliveries ở các subscriptions** theo mô hình minh họa. Lượng dữ liệu lưu và activity của consumers cũng có thể lớn hơn.

Chi phí thực phụ thuộc tier, số operations, compute/broker capacity, network, Log Analytics và retention. Không dùng số 2,5 triệu như số billable operations chính thức của Service Bus; phải tham chiếu chính sách giá của tier/region hiện hành.

### 16.3. Khi nào dùng Standard hay Premium?

| Tiêu chí | Standard | Premium |
| --- | --- | --- |
| Topics/subscriptions | Có | Có |
| Kiểu workloads | Workload nghiệp vụ với yêu cầu phù hợp mô hình Standard | Workload cần resource isolation/công suất ổn định hơn |
| Compute model | Theo tier Standard | Dành capacity theo mô hình Premium |
| Chi phí nền | Theo cấu trúc tính phí Standard | Có thể có chi phí capacity provisioned đáng kể |
| Throughput và tính ổn định | Phải load test theo tải thực | Cần sizing messaging units/resources và load test |
| Networking, quotas và các khả năng riêng | Phụ thuộc SKU/tính năng | Phụ thuộc tier và cấu hình |

Không chọn Premium chỉ vì “có filter SQL”: **Standard cũng hỗ trợ topics/subscriptions/rules**. Ngược lại, không mặc định Standard đáp ứng mọi throughput/SLO chỉ vì các rules chạy đúng chức năng.

### 16.4. Ước tính từ business workload

Giả sử 50.000 events/giờ, trung bình:

- 20% thuộc fulfillment VN.
- 8% thuộc fraud review.
- 100% thuộc audit-all.

Mô hình đơn giản:

~~~text
Published events/hour = 50.000

fulfillment-vn        = 10.000 selected/hour
fraud-review          =  4.000 selected/hour
audit-all             = 50.000 selected/hour

Total across subscriptions ≈ 64.000 selected deliveries/hour
~~~

Các tập có thể giao nhau; phép cộng trên **đếm theo subscription**, không phải unique event IDs. Kết quả cần kiểm chứng với distribution thực, cấu hình rules, duplicate detection, TTL và consumer behavior.

## 17. Runbook: message “mất”, nhận sai hoặc nhận trùng

### 17.1. Bảng khoanh vùng nhanh

| Triệu chứng | Nguyên nhân có thể | Bước kiểm tra |
| --- | --- | --- |
| Publisher báo gửi thành công, consumer không có message | Rule không match | Properties/kiểu/case, rules, `$Default`, publish timestamp |
| Consumer nhận mọi event dù chỉ muốn VN | `$Default` còn TRUE | Liệt kê rules và xóa đúng mặc định nếu được phép |
| VN OrderCreated không nhận | `AND` expression sai hoặc thiếu property | Kiểm tra `eventType`/`region` thực tế |
| Fraud không nhận high-value | `amount` sai kiểu/string hoặc threshold | Kiểm tra metadata numeric và filter |
| Một message xuất hiện ở nhiều subscriptions | Fan-out đúng thiết kế | So khớp expected matrix |
| Consumer thấy event trùng | Retry, message redelivery, duplicate publish, overlapping rules/actions | IDs, delivery count, lock logs, filters |
| Có messages ở DLQ | Lỗi processing, TTL hoặc đánh giá rule/forwarding theo policy | DLQ reason, max delivery, transfer DLQ |
| Messages ở subscription nguồn biến mất | Auto-forwarding đang bật | Kiểm tra target và transfer status |
| Rules mới không ảnh hưởng backlog cũ | Filter áp dụng khi message được route | Kiểm tra message enqueue time |
| Không tạo topic được | Namespace dùng Basic hoặc thiếu quyền | SKU/role/quota |
| SQL filter báo lỗi parse | Syntax/escaping không hợp lệ | Review biểu thức, API/SDK diagnostics |
| Queue receiver hoạt động nhưng topic subscription receiver không | Sai entity type/subscription/rights | Namespace, topic/subscription names |
| Azure SDK Unauthorized | Data-plane RBAC/SAS thiếu hoặc chưa propagation | Identity/scope và network |
| Message bị delay/timeout | Throttling, consumer slow, scale/backlog | Azure Monitor và consumer traces |

### 17.2. Quy trình chẩn đoán từng tầng

**Bước 1 — Xác định thông điệp**

Ghi `MessageId`, `CorrelationId`, `eventType`, `region`, `amount`, mốc UTC và tên topic. Không cần ghi full payload chứa dữ liệu nhạy cảm.

**Bước 2 — Xác minh publisher**

Có gửi vào đúng namespace/topic không? Có dùng identity đủ quyền Sender? Message ID có trùng trong duplicate detection window không? Body và application properties có thực sự được set riêng không?

**Bước 3 — Đọc rules của subscription đích**

Liệt kê rule names, types, SQL expressions, actions và sự tồn tại của `$Default`. Kiểm tra logic `AND`/`OR` và loại dữ liệu.

**Bước 4 — Đánh giá expected match thủ công**

Ví dụ:

~~~text
Message:
  eventType = OrderCreated
  region = TH
  amount = 15000000

fulfillment-vn:
  OrderCreated AND VN  → FALSE

fraud-review:
  OrderCreated AND amount>=10000000 → TRUE

audit-all:
  $Default TRUE → TRUE
~~~

Expected: chỉ Fraud + Audit. Nếu Fulfillment cũng nhận, kiểm tra `$Default`/overlapping rule hoặc backlog cũ.

**Bước 5 — Kiểm tra entity state**

Đọc active/dead-letter counts, TTL, auto-forwarding và receiver activity. Nếu có session-enabled subscription, xác minh receiver đang nhận sessions đúng.

**Bước 6 — Kiểm tra consumer**

Xem `PeekLock`/completion, delivery count, exceptions, idempotency, connection pool và concurrency. Nếu message có trong peek nhưng worker không nhận, lỗi khả năng lớn nằm ở receiver/permission/processing hơn là filter.

**Bước 7 — Sửa đúng nguyên nhân và thử lại**

Không xóa nguyên topic hoặc purge DLQ chỉ để giảm counter. Thay rule phải có IaC/review và kiểm thử trên batch riêng. Giám sát cả kết quả **được chọn** và **bị loại**.

### 17.3. Lưu ý khi test các hành vi âm tính

Nếu gửi E2 (TH) và thấy không có ở `fulfillment-vn`, đó là hành vi mong muốn. Nhưng để xác minh E2 không bị “mất” do publisher, hãy kiểm tra cùng `MessageId` ở `audit-all`. Đây là lợi ích của subscription audit nhận tất cả trong môi trường test.

## 18. Quy trình thay đổi rules trên production

### 18.1. Trước khi đổi

- Ghi rõ ticket, owner, mục tiêu và impacted subscriptions.
- Lưu snapshot cấu hình rules cũ, kể cả `$Default`, SQL actions và forwarding.
- Xác định producers/consumers liên quan và event schema version.
- Viết **routing truth table** gồm happy paths và negative cases.
- Đánh giá backlog cũ, TTL, DLQ và traffic đang xử lý.
- Đánh giá chi phí/throughput nếu tăng số subscriptions/rules.
- Chọn cửa sổ thay đổi, rollback và cơ chế theo dõi.

### 18.2. Canary với subscription mới

Một phương án ít tác động hơn sửa rule production trực tiếp:

1. Tạo `fulfillment-vn-v2` cùng topic nhưng rule mới.
2. Gửi các sự kiện kiểm thử có batch ID riêng.
3. So sánh tập messages của v1 và v2 bằng **peek** hoặc consumer được thiết kế chỉ test.
4. Khi rule mới đạt yêu cầu, deploy consumer version mới hoặc chuyển reader theo kế hoạch.
5. Theo dõi backlog của v1; không xóa v1 cho đến khi hoàn tất cutover.
6. Dọn entity cũ theo chính sách retention và change approval.

**Cẩn thận:** tạo subscription v2 trên topic đang có production traffic sẽ bắt đầu nhận **messages thực phù hợp kể từ lúc được tạo**. Cần phối hợp với các đội quản trị dữ liệu và không dùng consumer test tạo side effects production.

### 18.3. Khi cần thay rule tại chỗ

- Tạo custom rule mới trước, xác minh hoạt động.
- Chỉ sau đó xóa rule cũ theo quy trình; lưu ý khoảng chuyển tiếp có thể có nhiều rules match hơn dự kiến.
- Nếu không cho phép overlap tạm thời, dùng cutover bằng subscription mới hoặc kế hoạch bảo trì riêng.
- Không làm nhiều thay đổi không liên quan trong cùng lần deploy.
- Sau đổi, gửi bộ message chuẩn và âm tính, xác minh trace + counts.
- Cảnh báo nếu xuất hiện `$Default` không mong muốn hoặc rule drift.

### 18.4. Rollback phải tính đến message đã route

Rollback expression không xóa những message được route sai trong khoảng sự cố, cũng không tái tạo những message đã không match và bị loại khỏi subscription. Có thể cần **replay** từ event store/audit subscription hoặc event log đáng tin cậy.

Muốn replay an toàn phải có:

- Nguồn dữ liệu có độ bền và quyền đọc hợp lệ.
- Batch IDs mới phù hợp duplicate detection policy.
- Idempotency của consumers.
- Ghi nhận event replay reason và owner.
- Tránh đưa lại event sensitive vào subscription không được phép.

Không tự giả định audit-all thay thế full event store vĩnh viễn: audit subscription cũng có TTL, quota và consumer có thể Complete messages.

## 19. Bài thực hành thiết kế routing

### 19.1. Phần A: xác định rules

Từ mô tả:

- Dịch vụ giao hàng chỉ xử lý `OrderCreated` ở `VN`.
- Dịch vụ fraud kiểm tra đơn tạo mới có `amount >= 10000000`.
- Dịch vụ audit nhận mọi event.

**Yêu cầu:** viết rule cho ba subscriptions và quyết định có giữ `$Default` không.

**Đáp án:**

~~~text
fulfillment-vn:
  SQL: eventType = 'OrderCreated' AND region = 'VN'
  Không giữ $Default

fraud-review:
  SQL: eventType = 'OrderCreated' AND amount >= 10000000
  Không giữ $Default

audit-all:
  TRUE / $Default
  Giữ rule mặc định
~~~

### 19.2. Phần B: tính tập kết quả

Cho các events:

| ID | eventType | region | amount |
| --- | --- | --- | ---: |
| A | OrderCreated | VN | 10.000.000 |
| B | OrderCreated | VN | 9.999.999 |
| C | OrderCreated | TH | 10.000.000 |
| D | OrderCancelled | VN | 12.000.000 |
| E | OrderCreated | *(missing)* | 12.000.000 |

Tự tính message nào thuộc từng subscription, sau đó đối chiếu:

- Fulfillment: **A, B**.
- Fraud: **A, C, E**.
- Audit: **A, B, C, D, E**.

### 19.3. Phần C: tìm lỗi AND/OR

Một đồng nghiệp tạo hai rules trong `fulfillment-vn`:

~~~text
Rule 1: eventType = 'OrderCreated'
Rule 2: region = 'VN'
~~~

**Hỏi:** điều gì xảy ra với event `OrderCancelled`, `region='VN'`?

**Đáp án:** vẫn có thể được chọn vì Rule 2 match. Muốn cả hai điều kiện, đặt trong **cùng SQL rule** với `AND` hoặc cùng correlation rule gồm hai equality properties.

### 19.4. Phần D: tìm lỗi `$Default`

Bạn thấy `fulfillment-vn` có custom rule chính xác và `$Default` = TRUE.

**Hỏi:** cần xử lý thế nào?

**Đáp án:** xác nhận namespace/subscription, ghi lại rule hiện tại, kiểm tra custom rule rồi **loại `$Default` của fulfillment-vn** nếu subscription chỉ được phép nhận các đơn VN mới. Không xóa audit-all default rule.

### 19.5. Phần E: metadata sai kiểu

Một publisher gửi:

~~~json
{
  "application_properties": {
    "eventType": "OrderCreated",
    "region": "VN",
    "amount": "25000000"
  }
}
~~~

**Hỏi:** có thể kết luận chắc chắn Fraud sẽ nhận vì 25.000.000 lớn hơn 10.000.000 không?

**Đáp án:** Không. `amount` đang là **string**, không phải integer. Phải sửa contract/publisher, kiểm thử behavior filter và quy trình xử lý evaluation exceptions; không dựa vào ép kiểu ngầm.

### 19.6. Phần F: thay rule và backlog

Lúc 09:00, `fulfillment-vn` vẫn có rule TRUE. 09:15, đội triển khai xóa `$Default` và chỉ để rule VN. 09:20, consumer đọc lại subscription và thấy event TH gửi lúc 09:05.

**Hỏi:** có phải rule mới không hoạt động?

**Đáp án:** chưa chắc. Event TH có thể đã được route vào subscription trước lúc đổi rule. Kiểm tra enqueue time và backlog cũ; filter mới không lọc lại message đã tồn tại.

### 19.7. Phần G: cross-tenant leak

Một subscription dành cho tenant A có SQL filter `tenantKey='A'` nhưng được cấp quyền Receive cho principal của tenant B.

**Hỏi:** hệ thống đã cách ly tenant an toàn chưa?

**Đáp án:** chưa. Filter không thay authorization; cần RBAC đúng scope, identity/source validation, network và review policies.

### 19.8. Phần H: thiết kế suite kiểm thử có thể lặp lại

Một test plan nên ghi:

| Đối tượng kiểm tra | Dữ liệu đầu vào | Kết quả mong đợi |
| --- | --- | --- |
| Happy path VN | OrderCreated/VN/12,5m | Cả 3 subscriptions |
| Happy path non-VN nhỏ | OrderCreated/TH/2m | Audit |
| Boundary threshold | OrderCreated/TH/10m | Fraud + Audit |
| Non-event | OrderCancelled/VN/15m | Audit |
| Missing region | OrderCreated/missing/20m | Fraud + Audit |
| Wrong amount type | OrderCreated/VN/"20m" | Chặn ở publisher hoặc theo policy malformed |
| Default rule regression | Bất kỳ event TH nhỏ | Không xuất hiện ở Fulfillment |
| Consumer crash | OrderCreated/VN/12,5m | Xử lý idempotent khi retry |
| Rule change midstream | Message trước/sau cutover | Đúng theo publish timestamp/rules hiệu lực |
| Auto-forwarding | Message match rule | Target nhận đúng, source behavior như thiết kế |

## 20. Câu hỏi tự kiểm tra

**Câu 1.** Topic khác queue ở điểm nào?

**Đáp án:** Topic hỗ trợ publish/subscribe với nhiều subscriptions có thể nhận các bản message phù hợp độc lập; queue dùng mô hình competing consumers trên một entity.

**Câu 2.** Có thể lọc JSON body trực tiếp bằng `amount > 10000000` không?

**Đáp án:** Không theo mô hình subscription SQL filters thông thường; phải đặt `amount` thành application property numeric hoặc thực hiện lọc trong consumer.

**Câu 3.** Hai rules `region='VN'` và `eventType='OrderCreated'` tương đương một rule dùng AND không?

**Đáp án:** Không. Rules ở subscription được kết hợp như điều kiện OR ở mức lựa chọn message; dùng một rule có AND nếu cần cả hai.

**Câu 4.** Tại sao subscription nhận mọi message dù custom filter chỉ chọn VN?

**Đáp án:** Có thể vẫn còn rule `$Default` TRUE hoặc rule khác bao phủ toàn bộ messages.

**Câu 5.** Correlation filter thích hợp nhất khi nào?

**Đáp án:** Khi so khớp equality trên một hoặc vài properties như eventType/region/tenantKey, không cần so sánh khoảng hay pattern.

**Câu 6.** Message không match rule có tự vào DLQ không?

**Đáp án:** Không. Không match nghĩa broker không chọn message vào subscription đó; DLQ phản ánh lỗi/điều kiện dead-letter khác.

**Câu 7.** Đổi filter có lọc lại messages đã ở subscription không?

**Đáp án:** Không. Routing xét theo rules tại thời điểm message được đưa vào subscriptions.

**Câu 8.** Message E1 match Fulfillment và Fraud. Đây là lỗi trùng không?

**Đáp án:** Không, nếu hai subscriptions có mục đích độc lập. Một business event có thể được fan-out tới nhiều subscribers.

**Câu 9.** Vì sao vẫn cần idempotency khi có duplicate detection?

**Đáp án:** Duplicate detection tại broker không ngăn tất cả consumer redeliveries hoặc các lần publish với IDs khác nhau.

**Câu 10.** Service Bus Basic có hỗ trợ topic/subscription không?

**Đáp án:** Không, cần Standard hoặc Premium theo tính năng.

**Câu 11.** `SessionId` và `CorrelationId` có cùng chức năng không?

**Đáp án:** Không. SessionId dùng cho semantics xử lý theo session khi được bật; CorrelationId thường dùng để liên kết messages/traces và cũng có thể dùng trong correlation matching.

**Câu 12.** Có thể dùng filter tenantKey thay cho Azure RBAC không?

**Đáp án:** Không. Filter chỉ quyết định routing theo dữ liệu do publisher cung cấp; quyền gửi/nhận/quản trị vẫn phải kiểm soát.

**Câu 13.** Tại sao auto-forwarding khiến receiver đọc subscription nguồn không thấy message?

**Đáp án:** Message phù hợp có thể được broker chuyển sang target theo cấu hình; kiểm tra queue/topic đích và transfer status.

**Câu 14.** Khi rule mới loại một số messages ngoài ý muốn, rollback filter có phục hồi chúng không?

**Đáp án:** Không tự động. Cần nguồn replay đáng tin cậy, quyền truy cập, batch IDs và idempotent consumers.

**Câu 15.** Vì sao không nên chỉ đo total message count để xác nhận routing?

**Đáp án:** Counts bị ảnh hưởng bởi fan-out, backlog cũ, duplicate detection, consumers khác, TTL và retry. Phải kiểm tra MessageIds và publish timestamps theo tập mong đợi.

## Ghi nhớ

- **Topic → Subscription → Rule** là chuỗi chính để định tuyến message theo event metadata trong Azure Service Bus.
- **SQL filters** dùng khi cần biểu thức logic, so sánh số, `IN`/`LIKE`; **correlation filters** phù hợp equality matching đơn giản.
- **Một rule có AND** khác với **nhiều rules OR** trong cùng subscription. Luôn kiểm tra và xử lý rule **`$Default`** theo mục tiêu.
- **Application properties** phải có tên, kiểu và giá trị được chuẩn hóa; SQL filters không tự duyệt JSON body.
- **Không match filter không phải DLQ**; đồng thời thay rule **không lọc lại backlog cũ**.
- Một event có thể tới nhiều subscriptions đúng thiết kế, nhưng consumers vẫn cần **idempotency, retries, DLQ và monitoring**.
- **Filters không thay RBAC/authentication**. Quản trị lifecycle bằng IaC, kiểm thử routing matrix và có rollback/replay plan.
- Quyết định tốt nhất dựa trên **đúng người nhận, đúng thời điểm, đúng kiểu dữ liệu**, đồng thời bảo đảm bảo mật, hiệu năng, chi phí và khả năng vận hành.
