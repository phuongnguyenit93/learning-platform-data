# Address settings, wildcard và phạm vi chính sách trong ActiveMQ Artemis

> **Chương:** Định tuyến Artemis  
> **Phạm vi:** Cơ chế `<address-settings>` trong `broker.xml` của **Apache ActiveMQ Artemis**: wildcard khớp tên address, thứ tự độ cụ thể, cách các giá trị được bổ sung từ cấu hình rộng hơn, và phạm vi tác động thực tế. Các ví dụ phục vụ hệ thống giao tiếp bất đồng bộ bằng JMS/queue/topic; trọng tâm là Artemis, không dùng cú pháp policy của ActiveMQ Classic thay thế.

## 1. Vấn đề cần giải quyết

Một broker Artemis phục vụ nhiều luồng cùng lúc:

- `orders.work`: hàng đợi công việc, consumer có thể rollback và nhận lại.
- `orders.events`: address multicast phân phát sự kiện cho các queue của Billing và Email.
- `payments.work`: hàng đợi thanh toán, có mức chịu tải và cách retry riêng.
- `DLQ` và `ExpiryQueue`: nơi nhận message lỗi hoặc hết hạn.

Chúng ta muốn đặt mặc định cho phần lớn address, nhưng điều chỉnh một nhóm như `orders.*` và một address đặc biệt như `orders.work`. Artemis cho phép làm điều này bằng các phần tử `<address-setting match="...">`.

Ví dụ: tất cả address của hệ thống nhận mặc định 10 lần delivery; nhóm `orders` giới hạn còn 5 lần, sử dụng paging và gửi message quá số lần thử vào DLQ; riêng `orders.work` chỉ cho tối đa 3 lần, chờ 2 giây trước lần giao lại. Ta cần biết **quy tắc nào khớp**, **giá trị nào có hiệu lực** và **giá trị đó thuộc address hay queue**.

Kết thúc bài học, bạn có thể:

1. Đọc đúng cấu trúc `address-settings` và vai trò của `match`.
2. Dùng `*` (một segment) và `#` (nhiều segment) theo quy ước wildcard mặc định của Artemis.
3. Dự đoán cấu hình có hiệu lực khi `#`, một tiền tố và một tên chính xác cùng khớp.
4. Nhận ra các trường hợp không thể suy đoán an toàn khi wildcard giao nhau.
5. Phân biệt cấu hình **theo address** với định tuyến anycast/multicast, queue filter và security settings.
6. Kiểm thử redelivery, DLQ, expiry, paging và việc auto-create trong đúng phạm vi address.

## 2. Đặt address settings vào đúng mô hình Artemis

Artemis tách ba lớp:

- **Address** là đích logic nhận message từ producer.
- **Routing type** quyết định chuyển message từ address đến queue theo **anycast** hoặc **multicast**.
- **Queue** là nơi consumer đọc message và theo dõi trạng thái chưa ACK.

Ví dụ một address `orders.events` có hai queue multicast: `billing.events` và `email.events`. Một message được publish đến `orders.events` sẽ được định tuyến tới cả hai queue khi chúng phù hợp; mỗi queue có backlog của riêng mình.

**Address settings** là chính sách broker **được tra cứu theo tên address**. Nó không tự tạo mô hình multicast, không tạo subscription cho từng dịch vụ và không chọn consumer nhận message. Nó điều chỉnh những khía cạnh như retry, DLQ, expiration, auto-create hoặc cách broker quản lý tài nguyên khi address chịu tải.

~~~mermaid
flowchart TD
    P["Producer gửi vào orders.events"] --> A["Address: orders.events"]
    AS["address-settings match orders.#"] -. "Cấu hình liên quan address" .-> A
    A --> R{"Routing type"}
    R -->|multicast| B["Queue: billing.events"]
    R -->|multicast| E["Queue: email.events"]
    B --> CB["Billing consumer"]
    E --> CE["Email consumer"]
~~~

**Hệ quả:** `<address-setting match="orders.#">` áp dụng cho **address** `orders.events`. Queue `billing.events` nằm dưới address này chịu những hành vi tương ứng của address, mặc dù **tên queue không bắt đầu bằng `orders.`**.

Ngược lại, `<address-setting match="billing.#">` sẽ **không** chỉ áp dụng cho queue tên `billing.events` nếu queue này thuộc address `orders.events`. Muốn chính sách độc lập theo từng queue, phải xem những tính năng cấu hình queue cụ thể hoặc thiết kế tách address phù hợp, thay vì nghĩ `match` lọc theo tên queue.

## 3. Vị trí cấu hình và các thuộc tính quan trọng

Một broker instance Artemis thường có `etc/broker.xml`. Bên trong phần tử `<core>`, ta khai báo tập `<address-settings>` gồm một hay nhiều `<address-setting match="...">`.

Đoạn tối giản:

~~~xml
<address-settings>
  <address-setting match="#">
    <max-delivery-attempts>10</max-delivery-attempts>
    <redelivery-delay>0</redelivery-delay>
  </address-setting>

  <address-setting match="orders.#">
    <max-delivery-attempts>5</max-delivery-attempts>
    <redelivery-delay>1000</redelivery-delay>
  </address-setting>
</address-settings>
~~~

Cách đọc:

- `match="#"` là mẫu rất rộng, dùng làm cấu hình nền.
- `match="orders.#"` dành cho nhóm tên address phân cấp bắt đầu bằng `orders`.
- `max-delivery-attempts` quy định giới hạn số lần delivery trước khi áp dụng chính sách dead-letter tương ứng.
- `redelivery-delay` là thời gian trễ bằng **mili giây** trước khi giao lại theo cơ chế broker.
- Hai mục trên **không tự quyết định** rằng mọi message đều có thể được giao đúng từng ấy lần: ACK, rollback, retry từ phía client, transaction và từng giao thức vẫn quyết định diễn biến thực tế.

Những nhóm tùy chọn thường thuộc address settings:

| Nhóm | Thuộc tính minh họa | Câu hỏi nghiệp vụ |
|---|---|---|
| Giao lại | `max-delivery-attempts`, `redelivery-delay`, `redelivery-multiplier`, `max-redelivery-delay` | Một message lỗi được thử lại bao nhiêu lần và khoảng cách giữa các lần? |
| Thư lỗi | `dead-letter-address` | Message không thể xử lý được đưa tới đâu? |
| Hết hạn | `expiry-address`, `expiry-delay` và giới hạn expiry tùy phiên bản | Message hết thời hạn được xử lý thế nào? |
| Backpressure | `max-size-bytes`, `address-full-policy` | Khi tồn đọng lớn, broker paging, chặn, từ chối hay làm gì? |
| Vòng đời tự động | `auto-create-addresses`, `auto-create-queues`, `auto-delete-addresses`, `auto-delete-queues` | Broker có được tự tạo/xóa tài nguyên không? |
| Định tuyến mặc định | `default-address-routing-type`, `default-queue-routing-type` | Kiểu routing được chọn thế nào khi tự tạo đích? |

Tên thuộc tính và khả năng tương thích thay đổi qua các phiên bản Artemis. Luôn đối chiếu với schema `broker.xml` và tài liệu của **phiên bản sẽ triển khai** trước khi đưa cấu hình mới vào production.

## 4. Cú pháp wildcard theo tên address

### 4.1. Dấu chấm phân tách segment

Theo cấu hình wildcard mặc định, Artemis dùng dấu chấm `.` làm dấu phân cách các thành phần tên:

~~~text
orders.eu.payment.created
  │    │      │      │
  └────┴──────┴──────┴── 4 segment
~~~

Ba loại thành phần cần nhớ:

1. **Literal** như `orders` hoặc `work`: phải khớp tên segment tương ứng.
2. **`*`**: khớp **đúng một** segment.
3. **`#`**: khớp **không hoặc nhiều** segment. Trong thực hành, thường dùng làm phần hậu tố mở rộng, chẳng hạn `orders.#`.

Các ký tự và dấu phân tách có thể được cấu hình lại tại phần `wildcard-addresses` của Artemis. Phần lớn ví dụ sử dụng mặc định `.`, `*`, `#`; nếu hệ thống thay đổi quy ước, phải sửa bảng khớp cho phù hợp. Không mang cú pháp `>` của ActiveMQ Classic sang Artemis.

### 4.2. Bảng kiểm tra khớp

| Mẫu trong `match` | Address | Kết quả | Giải thích |
|---|---|---|---|
| `#` | `orders.work` | Khớp | Mẫu bao phủ mọi đường tên |
| `orders.work` | `orders.work` | Khớp | Tên chính xác |
| `orders.work` | `orders.WORK` | Không | Chữ hoa/thường khác nhau |
| `orders.*` | `orders.work` | Khớp | `*` đại diện một segment |
| `orders.*` | `orders.eu.work` | Không | Có hai segment phía sau `orders` |
| `orders.#` | `orders.work` | Khớp | `#` bao phủ hậu tố |
| `orders.#` | `orders.eu.payment.work` | Khớp | Hậu tố có nhiều cấp |
| `orders.#` | `payments.work` | Không | Segment đầu khác |
| `orders.*.created` | `orders.eu.created` | Khớp | Một segment ở giữa |
| `orders.*.created` | `orders.eu.payment.created` | Không | Nhiều hơn một segment ở giữa |
| `orders.eu.#` | `orders.eu.payment.created` | Khớp | Tiền tố cụ thể rồi tới hậu tố mở |
| `orders.eu.#` | `orders.us.payment.created` | Không | Segment `eu` khác `us` |

Vì `#` có thể khớp **0 segment**, một số trường hợp biên như tên bằng đúng tiền tố cần được kiểm tra trên phiên bản/cấu hình sử dụng. Với yêu cầu quan trọng, khai báo entry exact cho `orders` thay vì dựa vào suy luận về `orders.#`.

Ví dụ, `orders.*` không phải là toán tử “chuỗi bắt đầu bằng `orders.`” theo nghĩa regex: nó chỉ khớp **một cấp** sau dấu chấm. Để khớp mọi hậu tố có nhiều cấp, dùng `orders.#`.

### 4.3. Wildcard ở address settings khác wildcard routing

Artemis còn hỗ trợ wildcard trong **định tuyến địa chỉ**: một queue hoặc subscription có thể dùng address pattern phù hợp tùy cấu hình wildcard routing. Đây là cơ chế khác với việc chọn address-setting theo `match`:

- `<address-setting match="orders.#">` là **phạm vi của cấu hình quản lý address**.
- Một địa chỉ hoặc subscription dùng wildcard là **quy tắc nhận/định tuyến message**.
- `<security-setting match="orders.#">` là **phạm vi áp dụng quyền**, nằm trong kho cấu hình bảo mật riêng.

Cả ba có thể dùng cú pháp wildcard tương tự, nhưng không có cùng tác dụng. Một `address-setting` khớp tên **không tự subscribe vào mọi message** của nhóm `orders`.

## 5. Độ cụ thể, giá trị được chọn và cơ chế bổ sung thuộc tính

### 5.1. Khớp từ rộng đến hẹp

Giả sử khai báo:

~~~xml
<address-settings>
  <address-setting match="#">
    <max-delivery-attempts>10</max-delivery-attempts>
    <redelivery-delay>0</redelivery-delay>
  </address-setting>

  <address-setting match="orders.#">
    <max-delivery-attempts>5</max-delivery-attempts>
    <redelivery-delay>1000</redelivery-delay>
  </address-setting>

  <address-setting match="orders.work">
    <max-delivery-attempts>3</max-delivery-attempts>
    <redelivery-delay>2000</redelivery-delay>
  </address-setting>
</address-settings>
~~~

Đối với tên `orders.work`, có ba mẫu cùng khớp: `#`, `orders.#` và `orders.work`. Tên exact cụ thể nhất, nên giá trị `max-delivery-attempts=3` và `redelivery-delay=2000` được ưu tiên.

| Address thực | Các mẫu khớp | Giá trị tối đa delivery | Redelivery delay |
|---|---|---:|---:|
| `orders.work` | `#`, `orders.#`, `orders.work` | 3 | 2.000 ms |
| `orders.events` | `#`, `orders.#` | 5 | 1.000 ms |
| `orders.eu.payment` | `#`, `orders.#` | 5 | 1.000 ms |
| `payments.work` | `#` | 10 | 0 ms |

Trong các trường hợp trên, mẫu lồng nhau có quan hệ cụ thể rõ ràng. Khi có hai mẫu **chéo nhau**, ví dụ `orders.*.retry` và `orders.eu.#` cùng khớp `orders.eu.retry`, không nên dựa vào vị trí các thẻ XML để suy đoán. Hãy kiểm tra effective settings trên broker theo phiên bản thật, hoặc thêm một quy tắc exact nhằm ghi rõ ý định.

### 5.2. Điểm khác với kiểu “chọn một policy”: Artemis có phân cấp giá trị

Artemis quản lý address settings bằng **kho cấu hình phân cấp**. Với các property hỗ trợ cơ chế bổ sung, một setting cụ thể có thể nhận **giá trị còn thiếu** từ các entry rộng hơn; giá trị được chỉ rõ ở mức cụ thể hơn sẽ được ưu tiên.

Xét:

~~~xml
<address-settings>
  <address-setting match="#">
    <redelivery-delay>0</redelivery-delay>
    <max-delivery-attempts>10</max-delivery-attempts>
  </address-setting>

  <address-setting match="orders.#">
    <dead-letter-address>DLQ</dead-letter-address>
    <redelivery-delay>1000</redelivery-delay>
  </address-setting>

  <address-setting match="orders.work">
    <max-delivery-attempts>3</max-delivery-attempts>
  </address-setting>
</address-settings>
~~~

Cấu hình hiệu lực cần kỳ vọng và kiểm tra đối với `orders.work`:

- `max-delivery-attempts=3`: được khai báo tại exact match.
- `redelivery-delay=1000`: entry exact không khai báo, nên giá trị cụ thể phù hợp của `orders.#` có thể được bổ sung.
- `dead-letter-address=DLQ`: từ `orders.#`.
- Những thuộc tính chưa khai báo ở đâu vẫn theo giá trị mặc định/thiết lập được hỗ trợ của broker.

**Không coi một `address-setting` là văn bản kế thừa XML thuần túy.** Việc bổ sung xảy ra theo cơ chế repository và cách từng thuộc tính được biểu diễn trong phiên bản Artemis. Muốn bảo đảm một giá trị vận hành quan trọng, nên khai báo tường minh ở entry quan trọng và kiểm tra **effective settings** khi triển khai.

### 5.3. Tránh cấu hình chồng chéo khó kiểm chứng

Ví dụ:

~~~xml
<address-setting match="orders.eu.#">
  <max-delivery-attempts>4</max-delivery-attempts>
</address-setting>
<address-setting match="orders.*.retry">
  <max-delivery-attempts>2</max-delivery-attempts>
</address-setting>
~~~

Address `orders.eu.retry` phù hợp với cả hai. Thay vì ngầm cho rằng entry “viết sau thắng”, hãy khai báo chủ ý:

~~~xml
<address-setting match="orders.eu.retry">
  <max-delivery-attempts>2</max-delivery-attempts>
</address-setting>
~~~

hoặc chuẩn hóa tên để các nhóm ít giao nhau. Nếu muốn dùng phân cấp để đặt defaults, ưu tiên cấu trúc dễ đọc `# → orders.# → orders.work`. Khi review thay đổi, lập một ma trận address thật và giá trị hiệu lực mong đợi như bảng ở trên.

## 6. Ví dụ cấu hình Artemis theo phạm vi nghiệp vụ

Đây là **đoạn trong phần tử `<core>`** của `broker.xml`, dùng cho lab và cần ghép vào bộ khung cấu hình hợp lệ đúng phiên bản. Đoạn này cố ý khai báo address/queue từ trước để có thể tắt auto-create cho nhóm `orders`.

~~~xml
<addresses>
  <!-- Queue công việc xử lý theo anycast -->
  <address name="orders.work">
    <anycast>
      <queue name="orders.work" durable="true"/>
    </anycast>
  </address>

  <!-- Một sự kiện được gửi đến hai queue subscription -->
  <address name="orders.events">
    <multicast>
      <queue name="billing.events" durable="true"/>
      <queue name="email.events" durable="true"/>
    </multicast>
  </address>

  <!-- Các đích dành cho điều tra message lỗi và quá hạn -->
  <address name="DLQ">
    <anycast>
      <queue name="DLQ" durable="true"/>
    </anycast>
  </address>
  <address name="ExpiryQueue">
    <anycast>
      <queue name="ExpiryQueue" durable="true"/>
    </anycast>
  </address>
</addresses>

<address-settings>
  <!-- Mặc định chung cho các address chưa được đặc tả -->
  <address-setting match="#">
    <max-delivery-attempts>10</max-delivery-attempts>
    <redelivery-delay>0</redelivery-delay>
  </address-setting>

  <!-- Phạm vi các address nghiệp vụ orders -->
  <address-setting match="orders.#">
    <dead-letter-address>DLQ</dead-letter-address>
    <expiry-address>ExpiryQueue</expiry-address>
    <max-delivery-attempts>5</max-delivery-attempts>
    <redelivery-delay>1000</redelivery-delay>
    <max-size-bytes>104857600</max-size-bytes>
    <address-full-policy>PAGE</address-full-policy>
    <auto-create-addresses>false</auto-create-addresses>
    <auto-create-queues>false</auto-create-queues>
  </address-setting>

  <!-- Riêng orders.work cần giãn cách retry lâu hơn và ít lần -->
  <address-setting match="orders.work">
    <max-delivery-attempts>3</max-delivery-attempts>
    <redelivery-delay>2000</redelivery-delay>
  </address-setting>
</address-settings>
~~~

### 6.1. Phân tích hiệu lực theo tên

| Address | Các setting cần chú ý | Nguồn khai báo |
|---|---|---|
| `orders.work` | Tối đa 3 lần, delay 2 giây | Exact `orders.work` |
| `orders.work` | DLQ/expiry, 100 MiB và paging, không auto-create | Nhóm `orders.#` bổ sung thuộc tính không được exact khai báo |
| `orders.events` | Tối đa 5 lần, delay 1 giây; DLQ/expiry; paging | Nhóm `orders.#` |
| `DLQ` | Default retry 10 lần, delay 0 | `#`; không nhận DLQ của nhóm `orders` |
| `ExpiryQueue` | Default retry 10 lần, delay 0 | `#` |
| `payments.work` (nếu có) | Default retry 10 lần, delay 0 | `#` |

Điểm dễ bỏ sót: queue `billing.events` **thuộc address `orders.events`**, nên các giá trị address settings được tra cứu theo `orders.events`. Đổi tên queue từ `billing.events` sang `billing-v2.events` không khiến broker tự chọn một `address-setting match="billing.#"`.

### 6.2. DLQ và expiry cần tồn tại theo routing phù hợp

Ở ví dụ này:

- `DLQ` và `ExpiryQueue` là **address riêng** có queue anycast để lưu message được broker chuyển tới.
- `dead-letter-address` dùng khi message vượt giới hạn delivery/redelivery theo chính sách.
- `expiry-address` dùng khi message hết hạn theo TTL/expiration.
- Khi một message đi vào DLQ, nó nằm ở **đích khác** so với `orders.work`; trong ví dụ đích DLQ không bắt đầu bằng `orders.` nên không nhận cùng policy nhóm `orders.#`.

Cần thiết kế riêng quyền truy cập và cách xử lý message trong DLQ/expiry. Không để consumer vận hành tự động replay tất cả message DLQ mà không phân biệt nguyên nhân lỗi và kiểm tra idempotency.

### 6.3. Auto-create false có hệ quả với JMS subscriber

Cấu hình:

~~~xml
<auto-create-addresses>false</auto-create-addresses>
<auto-create-queues>false</auto-create-queues>
~~~

hạn chế việc broker tự tạo address/queue cho các tên khớp. Đây là cách phát hiện lỗi chính tả destination và kiểm soát vòng đời tài nguyên trong lab có queue khai báo sẵn.

Tuy nhiên, **JMS durable topic subscriptions có thể cần tạo queue nội bộ**. Nếu ứng dụng dùng API tự tạo durable subscription trên `orders.events` mà `auto-create-queues=false`, hành vi sẽ phụ thuộc phiên bản, quyền và mô hình tạo subscription. Bạn phải **tạo queue phù hợp trước hoặc điều chỉnh policy** theo phương án đã chọn; đừng bật cấm tự tạo và đồng thời giả định mọi subscription tạo động vẫn hoạt động.

Trong ví dụ đã chủ động khai báo `billing.events` và `email.events`. Consumer đọc queue tương ứng bằng FQQN, nên không cần tạo một durable subscription mới bằng cách gọi JMS `createDurableConsumer`.

## 7. Phạm vi của address settings: những gì được điều chỉnh và những gì không

### 7.1. Tác động theo address, không phải mỗi consumer

Một address multicast có ba queue cho ba nhóm. `max-size-bytes` và `address-full-policy` là chính sách quản lý **dung lượng/tắc nghẽn ở phạm vi address**, không phải ba hạn mức riêng biệt tự động bằng nhau cho ba queue.

Nếu queue Billing chậm và tồn đọng kéo dài, nó vẫn có thể gây paging hoặc áp lực tài nguyên cho address `orders.events` và cả broker. Việc Email xử lý nhanh không có nghĩa limit memory của address sẽ không bị chạm.

Đối với cấu hình cần cách ly dung lượng hoặc retry giữa hai nghiệp vụ, cân nhắc thiết kế **address tách biệt**, hoặc những thuộc tính có thể đặt trực tiếp ở queue và cơ chế phân phối phù hợp. Đừng kỳ vọng đặt hai `address-setting match="billing.#"` và `match="email.#"` sẽ chia tách chính sách của hai queue cùng nằm dưới `orders.events`.

### 7.2. Không thay đổi routing type chỉ bằng `match`

Anycast hay multicast là lựa chọn routing của address và queue; address settings chỉ có thể ảnh hưởng **mặc định khi tạo đích**, ví dụ `default-address-routing-type` hoặc `default-queue-routing-type`, nếu thiếu khai báo rõ và version hỗ trợ.

Khi đã khai báo:

~~~xml
<address name="orders.events">
  <multicast>
    <queue name="billing.events"/>
    <queue name="email.events"/>
  </multicast>
</address>
~~~

việc `orders.events` khớp `orders.#` không biến hai queue thành anycast, không tự tạo thêm nhóm fan-out và không thay selector/filter của consumer.

### 7.3. Security, routing và queue filter thuộc phạm vi khác

| Nhu cầu | Nơi thường cấu hình | Vì sao không nhầm với `address-settings` |
|---|---|---|
| Cho phép user gửi/đọc/tạo queue | `security-settings`, roles, security manager | Kiểm soát **quyền** |
| Đặt anycast/multicast và queue | `addresses` hoặc thao tác quản trị | Kiểm soát **đường phân phối** |
| Chỉ nhận message có thuộc tính nhất định | Queue filter / JMS selector | Kiểm soát **message nào đủ điều kiện nhận** |
| Chuyển hoặc nhân luồng qua một địa chỉ khác | Divert và cấu hình routing liên quan | Kiểm soát **đường chuyển message** |
| Retry, expiry, DLQ, paging, auto-create theo address | `address-settings` | Kiểm soát **hành vi broker đối với address** |

Cùng một mẫu wildcard có thể xuất hiện trong `address-settings` và `security-settings`, nhưng hai cấu hình nằm trong **hai hệ tra cứu khác nhau**. Một setting khớp không tự cấp quyền gửi hay tiêu thụ.

### 7.4. Queue Name và FQQN

Artemis có cú pháp **Fully Qualified Queue Name** thường ở dạng `address::queue`, ví dụ:

~~~text
orders.events::billing.events
~~~

Cú pháp này giúp client chỉ định queue cụ thể khi protocol hỗ trợ. Trong `<address-setting match="...">`, **hãy khớp tên address `orders.events`**, không ghi `match="orders.events::billing.events"` để kỳ vọng chỉ áp dụng cho Billing.

## 8. Bốn nhóm setting cần hiểu bằng hành vi

### 8.1. Redelivery: vì sao một message quay lại?

Giả sử consumer dùng **transacted JMS session** và xử lý lỗi nên gọi rollback:

~~~text
orders.work
  delivery #1  -> xử lý lỗi -> rollback
  chờ 2.000 ms
  delivery #2  -> xử lý lỗi -> rollback
  chờ 2.000 ms
  delivery #3  -> xử lý lỗi -> rollback
  ... chính sách chuyển sang DLQ khi tới ngưỡng
~~~

Với `match="orders.work"` và `max-delivery-attempts=3` trong ví dụ, số lần giao được kiểm soát theo chính sách broker và trạng thái message. Sau ngưỡng, message có thể được đưa tới `DLQ` đã cấu hình ở nhóm `orders.#`.

Phân biệt:

- **ACK / commit**: message đã hoàn thành với queue.
- **Rollback / session recovery**: message có thể được giao lại, tùy policy.
- **Redelivery delay**: khoảng trễ trước lần giao tiếp theo.
- **DLQ**: địa chỉ xử lý lỗi khi không tiếp tục giao bình thường.
- **JMSXDeliveryCount**: thuộc tính hỗ trợ quan sát số lần delivery; không phải khóa chống xử lý trùng của nghiệp vụ.

Nếu consumer ghi dữ liệu vào database thành công rồi crash **trước ACK**, broker có thể giao lại. Hệ thống vẫn cần idempotency key như `eventId` hoặc `orderId`; thay `max-delivery-attempts` không giải quyết được duplicate ở tầng nghiệp vụ.

### 8.2. Expiry: thời gian sống không đồng nghĩa với số lần retry

TTL (time-to-live) do producer đặt hoặc chính sách broker quyết định thời điểm message hết hạn. Một message chưa kịp xử lý nhưng **hết TTL** có thể được chuyển tới `expiry-address` hoặc bị loại theo cấu hình.

Ví dụ producer gửi thông điệp giữ tối đa 60 giây; consumer ngắt 3 phút. Dù queue durable, thông điệp quá hạn không được xem như message bình thường còn hiệu lực khi consumer trở lại.

**Phân biệt DLQ và expiry:** DLQ thường do thất bại nhiều lần; expiry do thời hạn đã hết. Nếu cần điều tra cả hai, khai báo đích riêng và theo dõi metric riêng.

### 8.3. Paging: áp lực bộ nhớ của address

Giả sử `orders.events` sử dụng:

~~~xml
<max-size-bytes>104857600</max-size-bytes>
<address-full-policy>PAGE</address-full-policy>
~~~

Khi lượng dữ liệu do address quản lý vượt ngưỡng áp dụng, broker có thể chuyển sang **paging** để quản lý backlog thông qua đĩa. Điều này **không có nghĩa** rằng 100 MiB là dung lượng tổng tối đa trên disk hoặc message sẽ bị xóa khi vượt mức.

Những kiểu chính sách khi address đầy như PAGE/BLOCK/FAIL/DROP (tùy phiên bản và cấu hình) thể hiện các quyết định khác nhau: ghi backlog ra paging store, chặn sender, báo lỗi hoặc bỏ message theo chính sách. Không chọn chỉ dựa vào throughput danh nghĩa. Đo thêm độ trễ producer, queue lag, tốc độ ACK, kích thước paging store và disk free.

### 8.4. Auto-create/auto-delete: kiểm soát vòng đời tài nguyên

Cấu hình theo address có thể quyết định broker được tự tạo address/queue hay tự xóa tài nguyên không còn được dùng. Hai rủi ro trái ngược:

- **Auto-create quá rộng**: lỗi chính tả `orders.wrok` có thể tạo đích khác, producer vẫn gửi được nhưng consumer không bao giờ đọc.
- **Auto-create quá chặt**: ứng dụng trông chờ tạo queue/subscription động có thể không khởi tạo được.

Các policy auto-delete cần được dùng cẩn thận cho durable subscriptions và queue có backlog. Consumer tắt không có nghĩa backlog không còn giá trị. Đánh giá quy trình tạo tài nguyên bằng cấu hình tĩnh, lệnh quản trị hoặc cơ chế provisioning của ứng dụng thay vì tùy tiện cho phép/khóa tự tạo ở mọi môi trường.

## 9. Ví dụ Java JMS thử redelivery trên `orders.work`

Ví dụ này dùng **Jakarta JMS** (package `jakarta.jms`) và Artemis Jakarta client; dependency điển hình là `org.apache.activemq:artemis-jakarta-client`. Chọn phiên bản tương thích broker, JDK và BOM của dự án. Không trộn `javax.jms` và `jakarta.jms` trong cùng mã.

Giả định Artemis lab đã chạy cấu hình ở mục 6 trên port `61616`, user `app` có quyền gửi/nhận `orders.work`, và queue đang rỗng để dễ quan sát. Mã gửi một message PERSISTENT, sau đó rollback lần đầu và commit ở lần giao tiếp theo.

~~~java
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public final class ArtemisAddressSettingsProbe {

    private static void logDelivery(String label, Message message)
            throws Exception {
        String count = message.propertyExists("JMSXDeliveryCount")
                ? String.valueOf(message.getIntProperty("JMSXDeliveryCount"))
                : "unavailable";
        System.out.println(label + " id=" + message.getJMSMessageID()
                + ", deliveryCount=" + count
                + ", redelivered=" + message.getJMSRedelivered());
    }

    public static void main(String[] args) throws Exception {
        ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory(
                        "tcp://localhost:61616",
                        "app", "lab-secret"); // Chỉ dùng giá trị giả trong lab

        // Producer: một message persistent với TTL đủ lâu cho lab.
        try (JMSContext producer =
                     factory.createContext(JMSContext.AUTO_ACKNOWLEDGE)) {
            Queue target = producer.createQueue("orders.work");
            producer.createProducer()
                    .setDeliveryMode(DeliveryMode.PERSISTENT)
                    .setTimeToLive(5 * 60_000L)
                    .send(target, "orderId=O-1001");
        }

        // Consumer: transacted session, lần đầu rollback, lần sau commit.
        try (JMSContext consumerContext =
                     factory.createContext(Session.SESSION_TRANSACTED)) {
            Queue target = consumerContext.createQueue("orders.work");
            JMSConsumer consumer = consumerContext.createConsumer(target);

            Message first = consumer.receive(5_000L);
            if (first == null) {
                throw new IllegalStateException("No initial delivery");
            }
            logDelivery("first", first);
            consumerContext.rollback(); // Chưa xác nhận xử lý thành công

            // Chính sách orders.work có redelivery-delay 2000 ms.
            Message second = consumer.receive(10_000L);
            if (second == null) {
                throw new IllegalStateException("No redelivery");
            }
            logDelivery("second", second);

            if (!(second instanceof TextMessage)) {
                consumerContext.rollback();
                throw new IllegalStateException("Unexpected message type");
            }
            String payload = ((TextMessage) second).getText();
            processIdempotently(payload);
            consumerContext.commit(); // Hoàn tất receive của JMS transaction
        }
    }

    private static void processIdempotently(String payload) {
        // Trong production, dùng unique eventId/orderId ở DB.
        System.out.println("Processed " + payload);
    }
}
~~~

Cách diễn giải kết quả:

1. Message đến `orders.work`, nên broker tra cứu `address-settings` theo address đó, không theo lớp Java hay tên consumer.
2. Rollback lần đầu khiến message có thể được giao lại sau khoảng delay đã cấu hình.
3. `commit()` của consumer transaction xác nhận receive trong broker. **Nó không tự gom transaction SQL** nếu `processIdempotently` ghi database.
4. Nếu consumer rollback cả các lần giao tiếp theo và chạm ngưỡng, message có thể được chuyển tới `DLQ` theo chính sách đã khai báo.
5. `JMSXDeliveryCount` và thời điểm delivery giúp quan sát thực tế; đừng khẳng định mỗi lần thử luôn cách nhau chính xác 2.000 ms vì scheduling và tải hệ thống gây sai lệch.

Mã chỉ là một phép thử của **redelivery**, chưa chứng minh mọi thuộc tính trong address-setting đều có hiệu lực. Việc gửi một message nhỏ không kích hoạt paging hay kiểm tra được giới hạn auto-create.

## 10. Bài thực hành: xác định policy hiệu lực trước khi chạy broker

### Bài A — Ba mức chính sách

Cho:

~~~xml
<address-settings>
  <address-setting match="#">
    <redelivery-delay>0</redelivery-delay>
    <max-delivery-attempts>12</max-delivery-attempts>
  </address-setting>

  <address-setting match="orders.#">
    <redelivery-delay>1500</redelivery-delay>
    <max-delivery-attempts>6</max-delivery-attempts>
    <dead-letter-address>DLQ</dead-letter-address>
  </address-setting>

  <address-setting match="orders.eu.#">
    <redelivery-delay>3000</redelivery-delay>
  </address-setting>

  <address-setting match="orders.eu.priority">
    <max-delivery-attempts>2</max-delivery-attempts>
  </address-setting>
</address-settings>
~~~

Hãy dự đoán giá trị `max-delivery-attempts`, `redelivery-delay` và `dead-letter-address` cho bốn address:

| Address | Attempts | Delay | Dead-letter address |
|---|---:|---:|---|
| `orders.eu.priority` | 2 | 3.000 ms | `DLQ` |
| `orders.eu.normal` | 6 | 3.000 ms | `DLQ` |
| `orders.us.priority` | 6 | 1.500 ms | `DLQ` |
| `payments.work` | 12 | 0 ms | Không được khai báo trong các entry này |

**Giải thích:** giá trị được chỉ rõ ở mức cụ thể hơn ưu tiên; thuộc tính không có ở mức exact hoặc nhóm hẹp được bổ sung từ nhóm phù hợp rộng hơn. Tính đúng của bảng cần được xác nhận bằng effective settings trên phiên bản Artemis dùng để vận hành.

### Bài B — Dễ nhầm `*` và `#`

Cho hai mẫu:

~~~xml
<address-setting match="orders.*">
  <max-delivery-attempts>4</max-delivery-attempts>
</address-setting>
<address-setting match="orders.eu.#">
  <redelivery-delay>2000</redelivery-delay>
</address-setting>
~~~

1. `orders.work` khớp `orders.*`.
2. `orders.eu.payment` **không** khớp `orders.*` vì có hai segment sau `orders`.
3. `orders.eu.payment` khớp `orders.eu.#`.
4. `orders.us.payment` không khớp `orders.eu.#`.

Nếu cần một policy bao phủ mọi cấp dưới `orders`, dùng `orders.#`. Với wildcard chéo nhau, bổ sung kiểm thử thay vì dựa vào thứ tự các thẻ XML.

### Bài C — Sai phạm vi queue

Giả sử:

~~~xml
<address name="orders.events">
  <multicast>
    <queue name="billing.events"/>
    <queue name="email.events"/>
  </multicast>
</address>
~~~

Người viết cấu hình muốn Billing nhận tối đa 2 lần rồi DLQ, Email nhận tối đa 7 lần, nên thêm:

~~~xml
<address-setting match="billing.#">
  <max-delivery-attempts>2</max-delivery-attempts>
</address-setting>
<address-setting match="email.#">
  <max-delivery-attempts>7</max-delivery-attempts>
</address-setting>
~~~

**Phân tích:** hai entry này không tạo chính sách riêng cho queue `billing.events` và `email.events`, vì **address thực của cả hai là `orders.events`**. Bài toán phải được thiết kế lại bằng cách tách address, chuyển message qua cơ chế phân phối phù hợp hoặc dùng cấu hình queue/phương án xử lý tương ứng được hỗ trợ. Không được giả định sửa `match` theo queue name là đủ.

### Bài D — Kiểm tra paging và auto-create

1. Dùng cấu hình mục 6, bảo đảm `orders.work` đã được khai báo sẵn.
2. Thử gửi tới tên sai `orders.wrok`; ghi nhận lỗi/khả năng tự tạo theo Artemis phiên bản đang chạy.
3. Kiểm tra console/management xem có address/queue sai tên xuất hiện không.
4. Dùng producer tạo backlog đủ lớn ở một address test được tách khỏi production; theo dõi memory usage và paging, không làm đầy disk.
5. So sánh với `payments.work` nếu address này đã được khai báo, vì nó chỉ nhận policy mặc định `#` trong ví dụ.
6. Khởi động lại broker và xác minh các thay đổi cấu hình thực sự được nạp. Đừng suy đoán mọi thuộc tính đã hot reload.

**Kết quả cần giải thích:** việc gửi vào tên sai phải được kiểm soát bằng provisioning/auto-create; một queue tồn đọng nhiều không nhất thiết chịu `max-size-bytes` của address khác; paging là cơ chế backlog, không phải DLQ.

## 11. Quy trình xác minh address settings trong vận hành

Khi sửa `broker.xml`, hãy làm theo thứ tự:

**Bước 1 — Xác định chính xác address.** Lấy tên address thực từ cấu hình broker hoặc management. Nếu consumer dùng FQQN `orders.events::billing.events`, địa chỉ dùng để match là `orders.events`.

**Bước 2 — Liệt kê mọi mẫu có thể khớp.** Với `orders.work`, ví dụ `#`, `orders.#` và `orders.work`. Kiểm tra delimiter và ký tự wildcard đã cấu hình, đồng thời so sánh chữ hoa/chữ thường.

**Bước 3 — Lập bảng giá trị hiệu lực.** Ghi rõ thuộc tính khai báo ở exact match và thuộc tính bổ sung từ mức rộng hơn. Tránh hai wildcard chéo nhau mà không có lý do rõ ràng.

**Bước 4 — Xác nhận cấu hình được nạp.** Tìm đúng broker instance, tệp `etc/broker.xml`, log khởi động và cơ chế áp dụng thay đổi của phiên bản. Thay đổi file không luôn lập tức đổi cấu hình của những address/queue đang hoạt động; cần kiểm tra reload/restart và cách áp dụng runtime.

**Bước 5 — Đọc metric và cấu hình runtime.** Dùng Artemis management API, CLI, JMX hoặc Web Console theo phiên bản để xem addresses, queues, số message ready/delivering, count, retry/DLQ, paging, disk và các tham số đã cấu hình. Khi công cụ có hỗ trợ truy vấn effective address settings, ưu tiên dữ liệu đó thay vì chỉ suy từ XML.

**Bước 6 — Gây lỗi có kiểm soát.** Thử rollback đến ngưỡng, gửi message có TTL ngắn, gửi tới destination typo và tạo backlog với consumer tạm dừng. Quan sát cả producer lẫn consumer. Những thử nghiệm này phải chạy trong lab hoặc môi trường cô lập.

**Bước 7 — Đảm bảo message không bị xử lý trùng.** Retry và failover có thể làm consumer nhận lại message đã ghi thành công vào database trước lúc ACK. Idempotency key ở ứng dụng vẫn là yêu cầu của giao tiếp bất đồng bộ đáng tin cậy, bất kể chính sách address settings.

### Những lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng xử lý |
|---|---|---|
| `orders.eu.payment` không nhận policy `orders.*` | `*` chỉ khớp một segment | Dùng `orders.#` nếu muốn nhiều cấp |
| Consumer queue `billing.events` không có retry policy mong muốn | `match` áp dụng theo **address**, không theo queue name | Kiểm tra address gốc hoặc tách address |
| DLQ trống dù consumer lỗi | Chưa vượt ngưỡng, transaction/ACK sai, không có dead-letter address/queue hợp lệ | Kiểm tra rollback, attempts, DLQ routing và quyền |
| Message không còn dù queue durable | TTL/expiry hoặc chính sách xóa khác | Kiểm tra expiration, expiry queue và journal |
| Queue test không được tạo tự động | `auto-create-queues=false` ở policy khớp | Provision queue hoặc đổi policy theo yêu cầu |
| Producer chậm khi backlog tăng | Paging, store I/O, giới hạn tài nguyên hoặc BLOCK policy | Xem max-size, full policy, disk và consumer lag |
| Một entry hẹp “thiếu” thuộc tính nhưng vẫn có giá trị | Hierarchical merge / broker default | Đọc effective settings và quy tắc bổ sung |
| Sửa XML nhưng thử nghiệm không đổi | Chưa nạp cấu hình vào broker/đích đang chạy | Xác minh instance, reload hoặc restart |
| Artemis không hiểu mẫu `orders.>` | Dùng nhầm wildcard của ActiveMQ Classic | Thay bằng `orders.#` theo cú pháp Artemis |

## 12. Checklist khi thiết kế chính sách theo address

Trước khi phát hành cấu hình Artemis, phải trả lời được:

- **Address nào thực sự tồn tại?** Tách rõ address, queue và tên FQQN phía client.
- **Naming convention là gì?** Segment, dấu phân tách, chữ hoa/thường có nhất quán không?
- **Mẫu nào khớp?** `*` đúng một segment, `#` nhiều segment; có tình huống chéo nhau cần entry exact không?
- **Thuộc tính nào lấy từ đâu?** Exact match, nhóm tiền tố, mặc định `#` hay mặc định của broker?
- **Phạm vi đúng chưa?** Retry/DLQ theo address, hay thực sự muốn chính sách riêng từng queue?
- **Routing nào đã định nghĩa?** Anycast/multicast và queue subscription có được provision không?
- **TTL, DLQ, expiry đã có đường đi hợp lệ chưa?** Các đích và quyền truy cập đã đủ chưa?
- **Address đầy sẽ làm gì?** PAGE, BLOCK, FAIL hoặc DROP đã được kiểm chứng với workload thật chưa?
- **Auto-create/delete có ảnh hưởng subscription động không?** Có nguy cơ tạo queue sai tên hoặc xóa backlog không?
- **Kiểm chứng runtime ra sao?** Có bảng expected settings, log, metric và thí nghiệm rollback/paging không?

## 13. Tổng kết

`address-settings` là **lớp chính sách quản lý theo tên address** của ActiveMQ Artemis. Với cú pháp mặc định, `*` khớp một segment và `#` khớp số segment mở rộng; các entry cụ thể hơn có thể ghi đè thuộc tính của entry rộng hơn, trong khi giá trị chưa khai báo có thể được bổ sung từ các mức phù hợp khác theo cơ chế phân cấp.

Thiết kế đúng đòi hỏi ba việc: **xác định address thực**, **vẽ được tập mẫu khớp theo độ cụ thể**, và **xác minh chính sách hiệu lực trên broker**. Khi phân biệt rõ address settings với routing, queue và security, bạn có thể đặt retry, DLQ, expiry, paging và auto-create đúng phạm vi mà vẫn tránh được việc một thay đổi cấu hình làm ảnh hưởng ngoài dự kiến tới các nhóm consumer.
