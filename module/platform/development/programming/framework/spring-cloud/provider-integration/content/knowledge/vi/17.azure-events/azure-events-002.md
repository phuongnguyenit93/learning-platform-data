# Partition, consumer group và thứ tự trong Event Hubs

Azure Event Hubs được thiết kế để tiếp nhận và phân phối luồng sự kiện với throughput cao. Để mở rộng hệ thống, Event Hubs chia một event hub thành nhiều **partition**. Mỗi ứng dụng tiêu thụ chọn một **consumer group** làm vị trí đọc logic riêng, rồi theo dõi tiến độ bằng **offset** và **checkpoint**. Ba khái niệm này quyết định cách dữ liệu được phân phối, khả năng chạy song song, phạm vi bảo đảm thứ tự và cách khôi phục sau khi consumer gặp sự cố.

Trong chương **Sự kiện Azure** của mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**, bài học giúp người học tích hợp Spring Boot với Azure Event Hubs qua Azure SDK và Spring Cloud Azure phù hợp. Trọng tâm là chọn partition key, phân chia consumer group, quản lý partition ownership, checkpoint đúng thời điểm, bảo vệ danh tính và quyền, xử lý event trùng hoặc sai thứ tự, kiểm thử scale-out và đánh giá throughput/độ trễ/chi phí.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vai trò của **partition**, **partition key**, **consumer group**, **offset**, **sequence number**, **checkpoint** và **partition ownership**.
- Phân biệt consumer group với queue, topic subscription và một instance consumer.
- Thiết kế partition key để phân phối tải đồng thời giữ thứ tự theo một khóa nghiệp vụ.
- Ước lượng mức song song thực tế theo số partition và số instance.
- Hiểu cách Event Processor Client chia partition giữa nhiều instance trong cùng consumer group.
- Thiết kế checkpoint, resume và replay an toàn khi process chết hoặc mất kết nối.
- Xử lý duplicate, poison event, hot partition, event đến sai thứ tự và thay đổi số partition.
- Tích hợp Event Hubs producer/consumer với Spring Boot, Managed Identity, Blob checkpoint store và Azure RBAC.
- Kiểm thử ordering, rebalance, checkpoint recovery, throughput và quyền truy cập trên môi trường riêng.

## 2. Mô hình dữ liệu của Event Hubs

Một event hub là một luồng sự kiện được chia thành các **partition**. Mỗi partition hoạt động như một log chỉ append theo thứ tự trong partition đó. Producer ghi event vào partition; consumer đọc tuần tự theo vị trí trong log. Event Hubs giữ event trong khoảng retention được cấu hình, vì vậy nhiều consumer có thể đọc cùng dữ liệu ở những thời điểm khác nhau.

~~~mermaid
flowchart TD
    P1["Producer: orders API"] --> H["Event Hub: order-events"]
    P2["Producer: payment service"] --> H
    H --> A["Partition 0<br/>E0, E1, E2, ..."]
    H --> B["Partition 1<br/>E0, E1, E2, ..."]
    H --> C["Partition 2<br/>E0, E1, E2, ..."]
    A --> CGA["Consumer group: analytics"]
    B --> CGA
    C --> CGA
    A --> CGF["Consumer group: fraud"]
    B --> CGF
    C --> CGF
~~~

Mỗi consumer group có vị trí đọc riêng trên từng partition. Consumer group analytics có thể đọc lại một đoạn lịch sử mà không làm thay đổi tiến độ của consumer group fraud. Trong cùng một consumer group, các instance phối hợp để phân chia partition, tránh việc tất cả instance đều đọc và xử lý toàn bộ stream như những consumer group độc lập.

### 2.1. Partition là đơn vị phân phối tải và thứ tự

Mỗi partition có chuỗi event riêng, với sequence number và offset tương ứng. Một event được ghi vào một partition cụ thể; event tiếp theo trong cùng partition được nối vào log đó. Partition là đơn vị chính để:
- Phân phối dữ liệu và xử lý song song.
- Duy trì thứ tự tương đối của event trong cùng partition.
- Gán ownership cho consumer instance trong một consumer group.
- Lưu tiến độ đọc/checkpoint độc lập.

Không có một thứ tự tổng thể tự động giữa các partition. Ví dụ event A ở partition 0 và event B ở partition 1 có thể được xử lý đồng thời; không thể kết luận event nào “đến trước” chỉ bằng cách so sequence number của hai partition.

### 2.2. Consumer group là một góc nhìn đọc độc lập

Consumer group không phải một instance Spring Boot. Nó là một **nhóm đọc logic** có tiến độ riêng. Nhiều instance của cùng ứng dụng logic thường dùng chung một consumer group để chia partition. Một ứng dụng logic khác cần đọc toàn bộ stream độc lập nên dùng consumer group khác.

Ví dụ:
- `order-analytics`: xử lý số liệu và báo cáo.
- `fraud-detection`: kiểm tra giao dịch bất thường.
- `order-archive`: lưu sự kiện vào data lake.
- `order-projection`: dựng read model cho API.

Mỗi nhóm có thể đọc cùng một event hub nhưng checkpoint riêng. Consumer group mặc định của Event Hubs thường có tên `$Default`; với workload production nên đặt tên rõ ràng theo ứng dụng logic, môi trường và mục đích. Không dùng tên consumer group riêng cho từng pod nếu mục đích là để các pod chia partition với nhau.

### 2.3. Offset và sequence number

**Sequence number** là số thứ tự tăng dần của event trong một partition. **Offset** là vị trí của event trong log partition, thường được SDK biểu diễn dưới dạng chuỗi. Cả hai đều có phạm vi **theo partition**, không phải số thứ tự toàn event hub.

Một event context thường cung cấp:
- Partition ID.
- Sequence number.
- Offset.
- Enqueued time.
- Event body và properties.

Dùng sequence number để theo dõi thứ tự trong partition hoặc phát hiện khoảng trống theo logic phù hợp. Dùng offset/sequence number làm điểm bắt đầu đọc lại khi cần. Không so sequence number giữa partition 0 và partition 1 như thể chúng thuộc cùng một bộ đếm toàn cục.

## 3. Producer chọn partition như thế nào?

Producer có thể định tuyến event theo một số cách:

1. **Partition key:** các event cùng key được định tuyến tới cùng partition theo cơ chế của dịch vụ, trong điều kiện partition layout ổn định. Đây là lựa chọn phổ biến khi cần giữ thứ tự theo một entity như `orderId`.
2. **Partition ID:** producer chỉ định trực tiếp partition đích. Cách này cho phép kiểm soát vị trí nhưng khiến ứng dụng phụ thuộc vào topology partition.
3. **Không chỉ định key/ID:** dịch vụ/SDK phân phối event theo cơ chế mặc định, phù hợp khi không cần thứ tự theo entity cụ thể và muốn phân phối tải.

Không nên tự tính hash để đoán partition ID. Dùng API/SDK để cung cấp partition key hoặc partition ID theo contract được hỗ trợ.

### 3.1. Chọn partition key theo entity cần có thứ tự

Giả sử một đơn hàng phát sinh các event:
- `OrderCreated`
- `PaymentAuthorized`
- `InventoryReserved`
- `OrderShipped`

Nếu các event của cùng `orderId` phải được quan sát theo thứ tự, dùng `orderId` làm partition key. Những đơn hàng khác nhau có thể đi tới partition khác nhau và được xử lý song song.

~~~mermaid
flowchart TD
    E1["orderId=1001<br/>OrderCreated"] --> K1["Partition key: 1001"]
    E2["orderId=1001<br/>PaymentAuthorized"] --> K1
    E3["orderId=1001<br/>OrderShipped"] --> K1
    K1 --> P0["Partition 0"]
    E4["orderId=2002<br/>OrderCreated"] --> K2["Partition key: 2002"]
    E5["orderId=2002<br/>PaymentAuthorized"] --> K2
    K2 --> P1["Partition 1"]
~~~

Cần chọn key có phân bố đủ đều. Nếu một key chiếm phần lớn lưu lượng, partition tương ứng trở thành **hot partition**. Ví dụ dùng `countryCode` làm key khi phần lớn đơn hàng đến từ một quốc gia có thể làm một partition nóng. Dùng `orderId` thường phân tán tốt hơn nếu số lượng order đủ lớn và tải không quá lệch.

### 3.2. Partition key và partition ID khác nhau

| Thuộc tính | Partition key | Partition ID |
|---|---|---|
| Mục đích | Gom event có quan hệ vào cùng partition | Gửi event tới partition cụ thể |
| Cách chọn | Producer cung cấp key nghiệp vụ | Producer chỉ định ID partition |
| Tính linh hoạt | Dịch vụ định tuyến key | Ứng dụng phụ thuộc partition topology |
| Trường hợp phù hợp | Thứ tự theo order/customer/device | Luồng đã phân vùng và quản trị partition ID tường minh |
| Rủi ro | Hot key, phân bố lệch | Thay đổi topology có thể làm logic định tuyến khó bảo trì |

Không nên trộn tùy tiện partition key và partition ID trong cùng luồng nếu chưa xác định rõ cách producer định tuyến. Partition key không phải khóa transaction và không thay thế kiểm soát concurrency ở database.

### 3.3. Thứ tự theo partition không phải thứ tự nghiệp vụ tuyệt đối

Event Hubs duy trì thứ tự append trong một partition. Nhưng nếu nhiều producer cùng gửi event có cùng partition key, thứ tự được quyết định bởi thời điểm dịch vụ tiếp nhận/ghi event, không nhất thiết bằng thời điểm nghiệp vụ xảy ra trong payload. Đồng hồ máy producer có thể lệch; request có thể bị mạng làm chậm; một producer có thể retry sau producer khác.

Nếu cần bảo đảm thứ tự nghiệp vụ:
- Dùng một nguồn phát có thứ tự hoặc cơ chế sequence/version do nghiệp vụ cấp.
- Đính kèm `aggregateId` và `aggregateVersion`/sequence trong event.
- Consumer kiểm tra version tiếp theo trước khi cập nhật trạng thái.
- Xử lý event đến trễ hoặc thiếu version bằng buffer, retry có giới hạn hoặc quarantine.
- Không chỉ sắp xếp theo timestamp client vì timestamp không bảo đảm thứ tự commit.

## 4. Consumer group và nhiều instance consumer

### 4.1. Một consumer group, nhiều instance

Trong cùng consumer group, Event Processor Client phối hợp thông qua **checkpoint store** để phân chia ownership. Một partition tại một thời điểm được một processor instance sở hữu trong consumer group đó. Các instance khác nhau có thể sở hữu các partition khác nhau.

Ví dụ event hub có 6 partition:
- 1 instance có thể sở hữu cả 6.
- 2 instance có thể chia 3 + 3.
- 3 instance có thể chia 2 + 2 + 2.
- 6 instance có thể có 1 partition mỗi instance.
- 10 instance không tạo ra 10 luồng đọc partition độc lập; tối đa vẫn bị giới hạn bởi 6 partition đang có, số instance dư có thể không sở hữu partition.

~~~mermaid
flowchart TB
    subgraph Hub["Event Hub: 6 partitions"]
      P0["P0"]
      P1["P1"]
      P2["P2"]
      P3["P3"]
      P4["P4"]
      P5["P5"]
    end
    subgraph Group["Consumer group: order-projection"]
      C1["Instance A"]
      C2["Instance B"]
      C3["Instance C"]
    end
    P0 --> C1
    P1 --> C1
    P2 --> C2
    P3 --> C2
    P4 --> C3
    P5 --> C3
~~~

Sơ đồ minh họa một cách chia cân bằng; thuật toán load balancing thực tế và thời điểm ownership thay đổi do SDK quản lý. Không dựa vào sơ đồ cố định để giả định pod nào luôn xử lý partition nào.

### 4.2. Nhiều consumer group, mỗi nhóm có bản sao tiến độ đọc riêng

Nếu analytics và fraud detection đều cần mọi event, tạo hai consumer group. Mỗi nhóm đọc tất cả partition độc lập; trong từng nhóm, các instance lại chia partition với nhau.

~~~mermaid
flowchart LR
    H["Event Hub"] --> P0["Partition 0"]
    H --> P1["Partition 1"]
    P0 --> A["Group: analytics"]
    P1 --> A
    P0 --> F["Group: fraud"]
    P1 --> F
    A --> AI["Analytics instances"]
    F --> FI["Fraud instances"]
~~~

Consumer group là ranh giới **tiến độ đọc**, không phải cơ chế bảo mật hoặc cô lập chi phí tuyệt đối. Các nhóm cùng dùng một event hub/namespace, vẫn chia sẻ capacity và chịu các giới hạn/quota liên quan. Quyền RBAC và scope của namespace/event hub phải được cấu hình riêng.

### 4.3. Scale-out không phải lúc nào cũng tăng throughput

Số partition giới hạn mức song song đọc trong một consumer group. Thêm instance khi số partition đã được sở hữu hết có thể không làm tăng throughput. Nếu partition nóng, tăng số instance cũng không chia nhỏ một partition cho nhiều owner cùng lúc trong cùng consumer group.

Các cách tăng năng lực:
- Tăng số partition nếu dịch vụ/tier cho phép và có kế hoạch về partition key.
- Cải thiện phân bố partition key để giảm hot partition.
- Tăng tốc xử lý mỗi event và giảm I/O đồng bộ trong callback.
- Dùng batch phù hợp, tránh checkpoint quá thường xuyên.
- Tối ưu Blob checkpoint store và network.
- Tách consumer group theo workload độc lập, nhưng tính cả capacity/chi phí đọc bổ sung.
- Đánh giá tier/capacity của Event Hubs và quota theo Region.

**Không tăng partition chỉ để tăng số pod.** Partition count ảnh hưởng thứ tự, phân bố key, ownership, checkpoint và chi phí; thay đổi topology cần được thử nghiệm.

## 5. Partition ownership và load balancing

Event Processor Client sử dụng checkpoint store để lưu thông tin ownership và checkpoint. Các processor instance trong cùng consumer group trao đổi thông tin qua store để biết partition nào đang được sở hữu và khi nào cần phân chia lại.

Một instance có thể:
- Nhận ownership của partition khi khởi động.
- Tiếp tục đọc từ checkpoint gần nhất hoặc vị trí khởi đầu nếu chưa có checkpoint.
- Mất ownership khi instance khác cần cân bằng hoặc instance hiện tại dừng.
- Nhường partition khi shutdown có kiểm soát.
- Nhận lại partition sau khi một instance khác gặp sự cố.

Ownership có thể thay đổi trong quá trình scale-out, scale-in, restart hoặc mất kết nối. Trong lúc rebalance, có thể xuất hiện khoảng thời gian gián đoạn xử lý và event được đọc lại từ checkpoint gần nhất. Consumer phải **idempotent**, không dựa vào giả định một callback chỉ được chạy đúng một lần.

### 5.1. Checkpoint store làm gì?

Checkpoint store lưu ít nhất hai nhóm trạng thái quan trọng:
- **Partition ownership/lease:** instance nào đang sở hữu partition trong consumer group.
- **Checkpoint:** vị trí đọc gần nhất mà consumer đã ghi nhận là đã xử lý.

Với EventProcessorClient, Blob Storage thường được dùng làm checkpoint store qua BlobCheckpointStore. Container phải tồn tại và workload cần quyền data-plane thích hợp, thường là **Storage Blob Data Contributor** trên container hoặc scope được thiết kế. Nếu storage checkpoint không truy cập được, processor có thể không cân bằng ownership hoặc không lưu tiến độ như mong muốn.

Checkpoint store không phải nơi lưu toàn bộ event stream; event vẫn nằm trong Event Hubs theo retention. Nó cũng không giống Event Hubs Capture:
- **Checkpoint:** consumer đã xử lý tới đâu.
- **Capture:** ghi bản sao dữ liệu stream ra Blob Storage/ADLS để lưu trữ hoặc xử lý batch theo cấu hình.

### 5.2. Một consumer group không chia partition giữa các nhóm khác nhau

Hai consumer group có checkpoint và ownership độc lập. Ví dụ:
- `orders-projection` có 3 instance.
- `orders-analytics` có 2 instance.

Không có chuyện analytics “nhường” partition cho projection chỉ vì projection đang thiếu instance; mỗi nhóm tự cân bằng trong phạm vi của mình. Điều này giúp các ứng dụng logic không phụ thuộc tiến độ nhau nhưng tăng lượng công việc đọc và có thể tăng chi phí/throughput sử dụng.

## 6. Offset, checkpoint và vị trí bắt đầu đọc

### 6.1. Offset và checkpoint khác nhau

Offset là vị trí của một event trong partition; checkpoint là bản ghi tiến độ consumer đã lưu bền vững. Một event có offset không có nghĩa consumer đã xử lý nó. Consumer chỉ nên cập nhật checkpoint **sau khi side effect cần thiết đã bền vững**.

~~~mermaid
sequenceDiagram
    participant EH as Event Hubs partition
    participant C as Consumer
    participant DB as Database
    participant CP as Blob checkpoint store
    EH->>C: Event offset 100
    C->>DB: Xử lý và commit event
    DB-->>C: Commit thành công
    C->>CP: Update checkpoint = 100
    CP-->>C: Checkpoint saved
~~~

Nếu cập nhật checkpoint trước khi commit database, consumer có thể chết sau checkpoint nhưng trước commit; khi khởi động lại nó bỏ qua event và gây mất xử lý. Nếu commit DB xong nhưng chết trước checkpoint, event có thể được đọc lại; đây là lý do cần idempotency.

### 6.2. Checkpoint thường xuyên hay theo batch?

| Chiến lược | Ưu điểm | Rủi ro/chi phí |
|---|---|---|
| Checkpoint mỗi event | Khoảng replay nhỏ sau sự cố | Nhiều thao tác checkpoint, I/O và độ trễ |
| Checkpoint sau N event | Giảm số thao tác checkpoint | Có thể replay nhiều event đã xử lý |
| Checkpoint theo thời gian | Dễ đặt ngân sách replay theo khoảng | Số event replay biến động theo throughput |
| Checkpoint sau batch xử lý bền vững | Gắn checkpoint với batch commit | Phải bảo đảm batch không bỏ sót event khi lỗi giữa chừng |

Không có một tần suất phù hợp mọi hệ thống. Chọn theo tốc độ event, chi phí Blob Storage, RPO xử lý chấp nhận được, thời gian xử lý và khả năng dedup. Nếu xử lý event theo batch, chỉ checkpoint tới event cuối cùng trong batch **sau khi mọi side effect trước đó đã được commit hoặc cách ly bền vững**.

### 6.3. Initial position và replay

Khi consumer group chưa có checkpoint, ứng dụng cần xác định vị trí bắt đầu đọc, chẳng hạn:
- **Earliest/earliest available:** đọc từ event sớm nhất còn trong retention.
- **Latest:** chỉ đọc event mới kể từ lúc bắt đầu.
- **Enqueued time:** bắt đầu từ thời điểm enqueue được chọn.
- **Offset/sequence number:** bắt đầu từ vị trí cụ thể nếu SDK/API hỗ trợ và vị trí còn hợp lệ.

Khi checkpoint đã tồn tại, processor thường resume theo checkpoint thay vì dùng initial position. Muốn replay:
- Dùng consumer group mới với initial position phù hợp; hoặc
- Điều chỉnh checkpoint có kiểm soát theo quy trình hỗ trợ; hoặc
- Dùng công cụ đọc riêng/processor riêng để xử lý lại khoảng thời gian.

Không reset checkpoint production trong khi consumer đang hoạt động nếu chưa hiểu ownership và tác động. Consumer group mới có thể đọc lại toàn bộ dữ liệu còn trong retention và tăng tải; cần giới hạn tốc độ replay và bảo vệ side effect.

### 6.4. Retention giới hạn khả năng replay

Event Hubs chỉ giữ event trong khoảng retention của cấu hình/tier. Nếu consumer ngừng lâu hơn retention, vị trí cũ có thể không còn dữ liệu để đọc. Checkpoint lưu offset không kéo dài thời gian lưu event. Nếu cần lưu lịch sử lâu dài hoặc replay nhiều tháng, hãy dùng Event Hubs Capture hoặc pipeline lưu event vào Blob Storage/ADLS/data lake theo chính sách retention riêng.

## 7. Ordering: giữ thứ tự ở phạm vi nào?

### 7.1. Thứ tự trong một partition

Trong một partition, event được append theo trình tự mà Event Hubs ghi nhận. Consumer đọc partition theo vị trí log. Đây là bảo đảm cơ bản để xử lý event theo key nếu producer định tuyến đúng.

Không có thứ tự toàn cục giữa nhiều partition. Ví dụ:
- `OrderCreated(1001)` ở P0.
- `OrderCreated(2002)` ở P1.
- `PaymentAuthorized(1001)` ở P0.

Consumer có thể xử lý event của P1 trước event của P0. Điều đó không vi phạm thứ tự của partition nào.

### 7.2. Thứ tự trong callback và xử lý song song

Ngay cả khi event cùng partition được đọc theo thứ tự, ứng dụng có thể tự làm đảo thứ tự nếu callback đẩy từng event vào executor bất đồng bộ và không giới hạn tác vụ đồng thời. Ví dụ event version 2 ghi DB xong trước version 1 vì version 1 xử lý chậm.

Nếu cần giữ thứ tự:
- Xử lý tuần tự trong từng partition hoặc từng aggregate key.
- Nếu dùng parallel processing, chỉ song song hóa các entity độc lập và giữ tuần tự theo key.
- Kiểm tra sequence/version trong database trước khi áp dụng.
- Chỉ checkpoint tới vị trí mà mọi event trước đó đã hoàn tất hoặc được cách ly theo policy.
- Tránh một tác vụ chậm làm checkpoint vượt qua event chưa hoàn tất.

### 7.3. Cần thứ tự toàn cục?

Một partition duy nhất có thể tạo một log chung cho toàn bộ event hub, nhưng giới hạn throughput và concurrency ở một partition. Nếu thực sự cần thứ tự toàn cục, hãy cân nhắc:
- Có thể mô hình hóa thành thứ tự theo aggregate/entity thay vì toàn hệ thống không?
- Có thể dùng sequence number do nguồn nghiệp vụ cấp và kiểm tra tại consumer không?
- Có thể chia event theo domain và chỉ yêu cầu ordering trong từng domain không?
- Nếu một luồng duy nhất là bắt buộc, chấp nhận giới hạn throughput và failure bottleneck nào?

Thứ tự toàn cục thường làm giảm khả năng mở rộng. Nên xác định **phạm vi thứ tự nhỏ nhất đáp ứng nghiệp vụ**.

## 8. Hot partition và phân bố tải

Hot partition xảy ra khi một hoặc vài partition nhận nhiều event hơn đáng kể so với phần còn lại. Nguyên nhân thường là:
- Partition key có cardinality thấp, như `country`, `eventType` hoặc một giá trị tenant lớn.
- Một tenant/device/entity phát sinh phần lớn traffic.
- Producer chỉ định partition ID cố định.
- Một consumer xử lý một loại event rất tốn CPU/I/O trong khi các partition khác nhẹ.
- Kích thước event khác nhau quá lớn.

Metric tổng event hub có thể trông ổn nhưng một partition bị nghẽn. Cần xem phân bố incoming bytes/messages, consumer lag và xử lý theo partition nếu telemetry hỗ trợ. Chọn partition key theo entity cần ordering nhưng vẫn phải đánh giá phân bố thực tế; không thể đồng thời gom tất cả event của một entity vào một partition và chia entity đó cho nhiều partition mà vẫn giữ thứ tự tự nhiên.

### 8.1. Các cách khắc phục

- Chọn key có cardinality và phân bố phù hợp, ví dụ `orderId` thay vì `countryCode` nếu cần ordering theo đơn.
- Tránh partition ID cố định nếu không có lý do rõ ràng.
- Giảm kích thước payload, tránh gửi dữ liệu không cần thiết.
- Tăng năng lực xử lý mỗi event và tránh gọi DB/HTTP tuần tự không cần thiết.
- Chia domain/stream nếu các workload có profile khác nhau.
- Đánh giá tăng partition count khi tier hỗ trợ và kiểm tra tác động tới key mapping.
- Không chia một aggregate sang nhiều partition nếu nghiệp vụ yêu cầu thứ tự mà không có cơ chế sequence/merge ở tầng ứng dụng.

### 8.2. Thay đổi partition count

Partition count là quyết định kiến trúc, không nên xem là một tham số autoscale vô hại. Khả năng thay đổi partition count phụ thuộc loại namespace/tier và giới hạn dịch vụ; một số cấu hình cho phép tăng nhưng không giảm. Thay đổi số partition có thể ảnh hưởng việc ánh xạ partition key sang partition, do đó có thể ảnh hưởng thứ tự quan sát khi cùng key trước và sau thay đổi được định tuyến khác nhau.

Trước khi thay đổi:
1. Kiểm tra khả năng của tier và giới hạn hiện hành.
2. Đánh giá key distribution và yêu cầu ordering.
3. Xác định consumer group/checkpoint behavior.
4. Thử nghiệm producer và consumer trên event hub test.
5. Lập kế hoạch chuyển đổi, theo dõi duplicate/replay và rollback khả thi.

Không hardcode partition ID trong nhiều service nếu topology có thể thay đổi; ưu tiên partition key theo hợp đồng nghiệp vụ.

## 9. EventProcessorClient trong Java

### 9.1. Vì sao dùng EventProcessorClient?

Azure SDK for Java cung cấp **EventProcessorClient** để đơn giản hóa:
- Phân chia partition ownership giữa nhiều instance.
- Load balancing và nhận lại partition khi instance khác dừng.
- Đọc event theo consumer group.
- Lưu checkpoint và ownership vào checkpoint store.
- Xử lý lỗi qua callback.

Nếu tự dùng EventHubConsumerClient, ứng dụng phải tự quản lý nhiều phần như partition enumeration, ownership, checkpoint, load balancing và recovery. Với Spring Boot worker chạy nhiều replica, EventProcessorClient thường là lựa chọn phù hợp khi cần consumer group phân tán.

### 9.2. Các thành phần cần cấu hình

| Thành phần | Mục đích | Lưu ý |
|---|---|---|
| Fully qualified namespace | Địa chỉ namespace Event Hubs | Ví dụ `orders-dev.servicebus.windows.net` |
| Event hub name | Luồng cần đọc | Mỗi consumer group đọc một event hub cụ thể |
| Consumer group | Vị trí đọc logic | Các instance cùng workload dùng chung group |
| TokenCredential | Danh tính workload | Managed Identity/DefaultAzureCredential |
| Blob container | Nơi lưu ownership/checkpoint | Container cần tồn tại và có quyền phù hợp |
| Process event callback | Xử lý từng event | Commit side effect trước checkpoint |
| Process error callback | Quan sát lỗi processor | Ghi partition, exception và correlation; không log secret |
| Initial position | Điểm bắt đầu khi chưa có checkpoint | Chọn earliest/latest/time/offset theo nghiệp vụ |

### 9.3. Cấu hình properties của Spring Boot

Ví dụ dưới đây là property **do ứng dụng tự định nghĩa**, không phải key mặc định áp dụng cho mọi phiên bản Spring Cloud Azure:

~~~yaml
app:
  event-hubs:
    namespace: orders-dev.servicebus.windows.net
    event-hub-name: order-events
    consumer-group: order-projection
    checkpoint-container-url: https://ordersdevstore.blob.core.windows.net/eventhub-checkpoints
~~~

Các giá trị là ví dụ. Production nên dùng namespace, hub, consumer group và checkpoint container riêng theo môi trường. Không dùng chung checkpoint container/consumer group cho hai ứng dụng logic khác nhau; điều đó có thể làm ownership và tiến độ đọc xung đột.

### 9.4. Tạo processor với Managed Identity

Ví dụ skeleton sử dụng Azure SDK trực tiếp; dependency cần có các artifact tương thích của:
- `azure-messaging-eventhubs`
- `azure-messaging-eventhubs-checkpointstore-blob`
- `azure-storage-blob`
- `azure-identity`
- Spring Boot configuration support

~~~java
import com.azure.identity.DefaultAzureCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.messaging.eventhubs.EventProcessorClient;
import com.azure.messaging.eventhubs.EventProcessorClientBuilder;
import com.azure.messaging.eventhubs.checkpointstore.blob.BlobCheckpointStore;
import com.azure.storage.blob.BlobContainerAsyncClient;
import com.azure.storage.blob.BlobContainerClientBuilder;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@ConfigurationProperties(prefix = "app.event-hubs")
record EventHubConsumerProperties(
        String namespace,
        String eventHubName,
        String consumerGroup,
        String checkpointContainerUrl) {}

@Configuration
@EnableConfigurationProperties(EventHubConsumerProperties.class)
class EventHubConsumerConfiguration {

    @Bean
    DefaultAzureCredential azureCredential() {
        return new DefaultAzureCredentialBuilder().build();
    }

    @Bean
    BlobContainerAsyncClient checkpointContainer(
            EventHubConsumerProperties properties,
            DefaultAzureCredential credential) {
        return new BlobContainerClientBuilder()
                .endpoint(properties.checkpointContainerUrl())
                .credential(credential)
                .buildAsyncClient();
    }

    @Bean(destroyMethod = "stop")
    EventProcessorClient eventProcessorClient(
            EventHubConsumerProperties properties,
            DefaultAzureCredential credential,
            BlobContainerAsyncClient checkpointContainer) {

        return new EventProcessorClientBuilder()
                .consumerGroup(properties.consumerGroup())
                .credential(
                        properties.namespace(),
                        properties.eventHubName(),
                        credential)
                .checkpointStore(new BlobCheckpointStore(checkpointContainer))
                .processEvent(context -> {
                    // 1. Validate schema và eventId.
                    // 2. Xử lý nghiệp vụ idempotent.
                    // 3. Commit database/quarantine bền vững.
                    processEventIdempotently(context.getEventData());

                    // Chỉ checkpoint sau khi side effect đã bền vững.
                    context.updateCheckpoint();
                })
                .processError(error -> {
                    // Ghi log exception và partition ID; không ghi payload/secret.
                    System.err.println(
                            "Event processor error: " + error.getThrowable());
                })
                .buildEventProcessorClient();
    }

    @Bean
    ApplicationRunner startEventProcessor(EventProcessorClient processor) {
        return args -> processor.start();
    }

    private static void processEventIdempotently(
            com.azure.messaging.eventhubs.EventData event) {
        // Thay bằng service xử lý có transaction và dedup theo eventId.
    }
}
~~~

Đây là **khung tích hợp minh họa**, cần kiểm tra method signatures theo phiên bản Azure SDK được BOM quản lý. Trong ứng dụng thực tế:
- Dùng logger có cấu trúc thay `System.err`.
- Chuyển xử lý nghiệp vụ vào service Spring riêng để có transaction, test và metrics.
- Cấu hình initial position rõ ràng cho consumer group chưa có checkpoint.
- Kiểm soát lifecycle start/stop và shutdown graceful.
- Đảm bảo checkpoint container tồn tại trước khi processor start.
- Nếu xử lý thất bại, không checkpoint vượt qua event chưa được xử lý hoặc chưa được lưu vào quarantine bền vững.
- Cân nhắc checkpoint theo batch/interval thay vì mỗi event nếu throughput cao; đo độ lớn replay và chi phí.

### 9.5. Producer dùng partition key

Ví dụ producer tạo batch với partition key theo order ID:

~~~java
import com.azure.messaging.eventhubs.CreateBatchOptions;
import com.azure.messaging.eventhubs.EventData;
import com.azure.messaging.eventhubs.EventDataBatch;
import com.azure.messaging.eventhubs.EventHubProducerClient;

public class OrderEventPublisher {
    private final EventHubProducerClient producer;

    public OrderEventPublisher(EventHubProducerClient producer) {
        this.producer = producer;
    }

    public void publish(String orderId, String eventJson) {
        CreateBatchOptions options =
                new CreateBatchOptions().setPartitionKey(orderId);

        EventDataBatch batch = producer.createBatch(options);
        if (!batch.tryAdd(new EventData(eventJson))) {
            throw new IllegalArgumentException(
                    "Event does not fit in an empty Event Hubs batch");
        }
        producer.send(batch);
    }
}
~~~

Khi dùng cùng partition key, các event của order có thể được định tuyến về cùng partition trong điều kiện topology ổn định. Producer cần:
- Dùng cùng một quy tắc key cho mọi event của cùng aggregate.
- Không để một service dùng order ID, service khác dùng customer ID cho cùng loại event nếu cần ordering chung.
- Ghi event ID và aggregate version trong payload.
- Xử lý send timeout theo cách idempotent; phản hồi mất không chứng minh event chưa được nhận.
- Tạo producer client dùng lại theo lifecycle bean, không khởi tạo mỗi request.

### 9.6. Vai trò của Spring Cloud Azure

Spring Cloud Azure cung cấp các starter và auto-configuration cho Spring Boot, nhưng mức abstraction/annotation hỗ trợ có thể khác theo major version. Trước khi chọn starter:
- Kiểm tra compatibility matrix giữa Spring Boot và Spring Cloud Azure BOM.
- Xác nhận API có hỗ trợ consumer group, checkpoint store, manual processing và callback cần thiết.
- Nếu cần kiểm soát partition ownership/checkpoint chi tiết, dùng Azure SDK EventProcessorClient trực tiếp trong một Spring-managed bean.
- Không tạo đồng thời hai processor client cho cùng workload/consumer group trong một instance nếu không có chủ đích.
- Cấu hình Managed Identity/DefaultAzureCredential theo môi trường; local developer credential không giống runtime identity trên Azure.

## 10. Checkpoint, duplicate và xử lý lỗi

### 10.1. Commit trước, checkpoint sau

Quy tắc an toàn phổ biến là **xử lý side effect bền vững trước rồi mới checkpoint**. Điều này tạo semantics ít nhất một lần (at-least-once) ở tầng consumer: event có thể được xử lý lại, nhưng không bị bỏ qua chỉ vì checkpoint đã tiến trước khi commit.

| Thứ tự | Sự cố | Hậu quả |
|---|---|---|
| Checkpoint → DB commit | Process chết giữa hai bước | Checkpoint đã vượt event, DB chưa ghi: có thể mất xử lý |
| DB commit → Checkpoint | Process chết giữa hai bước | DB đã ghi, checkpoint cũ: event được đọc lại |
| DB commit + dedup → Checkpoint | Process chết giữa hai bước | Event đọc lại nhưng dedup ngăn side effect lặp |
| Quarantine bền vững → Checkpoint | Event sai schema không thể xử lý | Event được cách ly, stream tiếp tục theo policy |

### 10.2. Idempotency ở consumer

Dùng event ID duy nhất và bảng inbox/processed-event:
- Ghi event ID và thay đổi nghiệp vụ trong cùng database transaction.
- Đặt unique constraint trên event ID hoặc `(consumerName, eventId)`.
- Nếu event đã xử lý, không lặp side effect.
- Nếu cùng event ID nhưng payload khác, ghi nhận conflict để điều tra.
- Giữ dedup record ít nhất trong thời gian có thể replay/duplicate theo chính sách nghiệp vụ.

Không chỉ dựa vào offset để chống trùng. Sau khi đổi consumer group hoặc replay, cùng event có thể được đọc lại từ offset khác; event ID là định danh nghiệp vụ bền hơn.

### 10.3. Poison event và checkpoint

Event sai schema hoặc dữ liệu vi phạm invariant có thể khiến callback lỗi lặp đi lặp lại. Event Hubs không cung cấp DLQ tích hợp theo mô hình queue như Service Bus. Có thể:
- Lưu raw event/metadata cần thiết vào **quarantine store** hoặc một queue xử lý lỗi riêng.
- Ghi partition ID, offset, sequence number, event ID và lý do lỗi.
- Chỉ checkpoint qua event đó sau khi đã lưu quarantine thành công và policy cho phép bỏ qua.
- Nếu không thể lưu bền vững, không checkpoint vượt qua event; dừng/đưa partition vào trạng thái cần can thiệp theo chiến lược vận hành.
- Có công cụ replay sau khi sửa schema/handler.

Không log toàn bộ payload nhạy cảm vào console hoặc Application Insights. Quarantine cũng là dữ liệu cần RBAC, retention, encryption và cleanup.

## 11. Thứ tự và concurrency ở tầng ứng dụng

Một partition chỉ có một owner trong một consumer group, nhưng điều đó không đảm bảo mọi side effect bên ngoài hoàn tất theo thứ tự nếu code tự xử lý song song.

Ví dụ:
1. Callback nhận `OrderStatusChanged(version=1)`.
2. Callback tiếp theo nhận `version=2`.
3. Ứng dụng đẩy hai event vào executor.
4. Version 2 commit trước version 1.
5. Trạng thái DB bị lùi nếu version 1 ghi sau.

Các cách bảo vệ:
- Xử lý tuần tự trong từng partition nếu thứ tự partition quan trọng.
- Dùng per-key serial executor khi một partition chứa nhiều entity độc lập nhưng cần thứ tự theo entity.
- Dùng optimistic concurrency với aggregate version.
- Chỉ checkpoint tới event cuối cùng của chuỗi đã xử lý an toàn.
- Giới hạn số event in-flight và backpressure để không tạo hàng đợi nội bộ vô hạn.

Nếu một partition có event xử lý rất lâu, xử lý tuần tự có thể làm partition lag. Có thể chuyển công việc nặng sang queue/worker sau khi ghi nhận event bền vững, nhưng phải giữ contract về thứ tự/version ở nơi thực hiện nghiệp vụ.

## 12. Bảo mật và phân quyền

Event Hubs và checkpoint Blob Storage là hai tài nguyên độc lập; workload thường cần quyền trên cả hai:
- **Event Hubs Data Receiver** trên event hub/namespace để đọc event.
- **Storage Blob Data Contributor** trên container checkpoint để tạo/cập nhật ownership và checkpoint.
- Producer cần **Event Hubs Data Sender**.
- Không cấp **Owner/Contributor** quản lý namespace chỉ để gửi/nhận event.
- Dùng Managed Identity hoặc workload identity; hạn chế SAS/connection string dài hạn.
- Tách namespace, event hub, consumer group và checkpoint container theo môi trường.
- Không dùng chung checkpoint container giữa các consumer logic khác nhau nếu có nguy cơ trùng tên/ownership và tiến độ.
- Kiểm tra private endpoint, DNS, firewall, TLS và network path từ runtime.

Consumer group không phải ranh giới bảo mật. Nếu một principal có quyền đọc namespace rộng, việc đổi consumer group không tự hạn chế quyền dữ liệu. RBAC scope cần gắn với namespace/event hub và role thích hợp.

### 12.1. Xác minh danh tính runtime

Local developer có thể dùng Azure CLI credential qua DefaultAzureCredential, còn ứng dụng trên App Service/AKS có thể dùng Managed Identity/Workload Identity. Vì vậy:
- Xác định principal thực tế khi chạy ở dev, staging và production.
- Gán data role tại đúng scope.
- Cấp quyền Blob checkpoint riêng.
- Không copy SAS token production vào local test.
- Log tenant/principal/resource context đã lọc, không log access token.

## 13. Monitoring và capacity planning

Các chỉ số quan trọng:

| Nhóm | Chỉ số | Vì sao cần theo dõi |
|---|---|---|
| Ingestion | Incoming messages/bytes, requests, throttled requests | Phát hiện producer vượt năng lực |
| Consumer | Outgoing messages, consumer lag, event age | Biết consumer có theo kịp stream không |
| Partition | Throughput và lag theo partition, ownership changes | Phát hiện hot partition hoặc rebalance liên tục |
| Checkpoint | Thời điểm checkpoint cuối, lỗi checkpoint, Blob latency | Phát hiện tiến độ đọc không được lưu |
| Processing | Event processing duration, failure count, duplicate suppressed | Tìm callback chậm và lỗi nghiệp vụ |
| Runtime | CPU, memory, thread pool, network, connection | Xác định bottleneck trong worker |
| Quarantine | Poison event count, replay count, backlog | Theo dõi event bị cách ly |
| Capacity/cost | Throughput/capacity units, tier, storage, network | Lập kế hoạch scale và chi phí |

Consumer lag có thể đo bằng chênh lệch giữa vị trí cuối partition và checkpoint/consumer position, hoặc bằng tuổi event chưa xử lý. Cần phân biệt:
- **Ingestion lag:** producer chưa gửi hoặc event chưa vào hub.
- **Processing lag:** event đã vào hub nhưng consumer xử lý chậm.
- **Checkpoint lag:** consumer đã xử lý nhưng chưa lưu checkpoint.
- **Business lag:** event đã được đọc nhưng side effect nghiệp vụ chưa hoàn tất.

Tăng partition chỉ giải quyết một phần nếu bottleneck nằm ở DB, Blob checkpoint store, network hoặc logic xử lý. Theo dõi từng partition giúp xác định có hot partition hay không.

## 14. Kiểm thử partition, consumer group và thứ tự

Dùng namespace/event hub test riêng, consumer group riêng và Blob checkpoint container riêng. Không reset checkpoint hoặc thay partition count của production để thử nghiệm.

| Kịch bản | Cách kiểm thử | Kết quả mong đợi |
|---|---|---|
| Partition key ổn định | Gửi nhiều event cùng orderId | Event của cùng key được route cùng partition theo topology ổn định |
| Nhiều key | Gửi event của nhiều orderId | Tải được phân bố, không có một partition nóng bất thường |
| Nhiều consumer instance | Scale từ 1 lên 3 instance cùng group | Ownership được phân phối lại, không có mỗi instance đọc toàn bộ stream |
| Nhiều consumer group | Analytics và fraud đọc cùng event hub | Hai nhóm có tiến độ độc lập |
| Instance chết trước checkpoint | Dừng worker sau side effect nhưng trước checkpoint | Event có thể replay; dedup ngăn side effect lặp |
| Checkpoint store không khả dụng | Chặn quyền/network tới Blob test | Processor báo lỗi; không giả định checkpoint đã lưu |
| Poison event | Gửi payload sai schema | Quarantine hoặc dừng theo policy; không checkpoint bỏ qua khi chưa lưu bền vững |
| Hot partition | Gửi phần lớn event với một key | Metric cho thấy lag/throughput lệch; xác định key skew |
| Event đến sai thứ tự nghiệp vụ | Gửi aggregate version đảo thứ tự | Consumer phát hiện version gap/stale event |
| Replay từ checkpoint cũ | Dùng consumer group test mới hoặc vị trí đọc đã định | Event được xử lý lại an toàn |
| Retention hết hạn | Mô phỏng consumer ngừng lâu hơn retention trên test | Có cảnh báo và runbook phục hồi từ archive nếu có |
| Quyền cross-environment | Dùng identity dev truy cập event hub prod | Bị từ chối bởi RBAC/network |

### 14.1. Test ordering bằng event ID và sequence

Payload test có thể gồm:
~~~json
{
  "eventId": "evt-1001-v2",
  "aggregateId": "order-1001",
  "aggregateVersion": 2,
  "eventType": "OrderPaid"
}
~~~

Gửi version 1 và 2 với cùng partition key. Consumer ghi lại partition ID, sequence number, offset, event ID và aggregate version. Kiểm tra:
- Cùng key có vào cùng partition không.
- Thứ tự enqueue có như kỳ vọng không.
- Consumer xử lý có giữ thứ tự khi bật concurrency không.
- Replay/duplicate có tạo side effect lặp không.
- Thay đổi số partition có ảnh hưởng routing không.

Không dùng timestamp hệ thống làm bằng chứng duy nhất về ordering. Ghi nhận sequence/version nghiệp vụ và metadata của Event Hubs.

## 15. Tình huống thực tế và cách xử lý

### Tình huống A: tăng pod nhưng throughput không tăng

Event hub có 4 partition; ứng dụng tăng từ 4 lên 12 pod trong cùng consumer group. Chỉ 4 pod có thể sở hữu partition ở trạng thái cân bằng, số pod dư không tạo thêm partition. Kiểm tra partition count, ownership và consumer lag. Nếu partition đang bão hòa, xem xét tăng partition khi được hỗ trợ, chọn key tốt hơn hoặc tối ưu handler trước khi tăng instance.

### Tình huống B: một khách hàng làm hot partition

Producer dùng `tenantId` làm partition key; một tenant lớn tạo 70% traffic. Tất cả event của tenant này vào một partition, consumer của partition đó chậm dù partition khác nhàn rỗi. Nếu thứ tự chỉ cần theo `orderId`, đổi key sang order ID có thể phân tán tốt hơn. Nếu thật sự cần thứ tự theo tenant, phải cân nhắc chia tenant thành shard logic và có sequence/merge, chấp nhận độ phức tạp bổ sung.

### Tình huống C: event bị xử lý lại sau khi pod restart

Consumer commit DB xong nhưng pod chết trước khi update checkpoint. Khi processor khởi động lại, event được đọc từ checkpoint cũ. Không phải Event Hubs mất event; đó là semantics at-least-once của consumer. Thêm inbox table/unique event ID để bỏ qua side effect đã commit, rồi checkpoint tiến tiếp.

### Tình huống D: event version 3 đến trước version 2

Nhiều producer gửi đồng thời hoặc ứng dụng xử lý song song làm version 3 hoàn tất trước version 2. Partition ordering chỉ phản ánh thứ tự append, không bảo đảm version nghiệp vụ luôn đến đúng thứ tự. Consumer cần aggregate version, kiểm tra gap và lưu event chờ hoặc quarantine; không ghi đè trạng thái chỉ theo thứ tự callback hoàn thành.

### Tình huống E: consumer mới đọc từ đầu và gây tải lớn

Một consumer group mới được tạo với initial position earliest, khiến nó đọc lại toàn bộ retention. Điều này có thể làm tăng outgoing throughput, Blob checkpoint I/O, DB writes và chi phí. Hãy kiểm soát replay rate, chạy ở môi trường riêng hoặc dùng archive, xác định side effect idempotent và theo dõi backlog.

## 16. So sánh nhanh với các mô hình messaging khác

| Khái niệm | Event Hubs | Service Bus | Kafka (khái niệm chung) |
|---|---|---|---|
| Đơn vị phân phối | Partition | Queue/topic subscription | Topic partition |
| Nhóm consumer | Consumer group | Receiver/subscription và competing consumers | Consumer group |
| Tiến độ | Offset + checkpoint | Settlement/Complete/lock | Offset commit |
| Replay | Trong retention theo offset | Không phải log replay; DLQ/resubmit theo lifecycle | Theo retention và offset |
| Ordering | Trong partition | Sessions để nhóm message có thứ tự | Trong partition |
| Scale consumer | Ownership partition trong group | Nhiều receiver cạnh tranh message | Partition assignment trong group |
| Phù hợp | Streaming/ingestion | Command/workflow | Distributed event log/streaming |

Event Hubs có endpoint tương thích Kafka cho một số client, nhưng không nên giả định mọi cấu hình, API, offset behavior hoặc feature của Kafka đều giống hệt. Dùng Azure SDK EventProcessorClient hay Kafka client là hai cách tích hợp có mô hình vận hành khác nhau; chọn một cách phù hợp và quản lý consumer group/offset/checkpoint nhất quán.

## 17. Checklist thiết kế trước production

- **Partition count:** phù hợp throughput, số consumer group, số instance và khả năng mở rộng; có kế hoạch khi cần thay đổi.
- **Partition key:** phản ánh entity cần ordering, đủ phân bố, tránh hot key; mọi producer dùng cùng contract.
- **Consumer group:** một group cho mỗi ứng dụng logic; các instance cùng workload dùng chung group.
- **Ownership:** dùng EventProcessorClient và checkpoint store phù hợp; hiểu rebalance và giới hạn parallelism theo partition.
- **Checkpoint:** chỉ cập nhật sau side effect bền vững hoặc quarantine; chọn tần suất theo replay budget.
- **Idempotency:** event ID ổn định, unique constraint/inbox, xử lý duplicate và replay.
- **Ordering:** phân biệt thứ tự partition với thứ tự nghiệp vụ; có aggregate version/sequence nếu cần.
- **Retention/replay:** initial position, retention, archive/Capture và quy trình replay rõ ràng.
- **Security:** Managed Identity, Event Hubs Data Receiver/Sender, Blob Data Contributor, scope tối thiểu, secret không lộ.
- **Operations:** metric per partition, lag, checkpoint age, rebalance, throttling, poison event và Blob checkpoint health.
- **Testing:** scale-out/in, crash trước/sau checkpoint, hot partition, event out of order, replay và cross-environment denial.
- **Cost:** capacity/tier, retention, Capture, checkpoint storage, network, log và số consumer group.

## 18. Tổng kết

**Partition** là đơn vị lưu trữ log, phân phối tải và bảo đảm thứ tự cục bộ. **Consumer group** là một vị trí đọc logic độc lập; các instance trong cùng group phối hợp để chia partition. **Offset** xác định vị trí event, còn **checkpoint** lưu tiến độ đã xử lý để resume/replay. Ba khái niệm này không thể thay thế nhau.

Khi tích hợp Event Hubs với Spring Boot, hãy chọn partition key theo phạm vi ordering của nghiệp vụ, thiết kế số partition theo throughput và concurrency, dùng EventProcessorClient để quản lý ownership, lưu checkpoint sau side effect bền vững, và làm consumer idempotent. Kiểm thử rebalance, hot partition, duplicate, replay và event sai thứ tự trên namespace riêng sẽ giúp hệ thống mở rộng có kiểm soát mà vẫn giữ được tính đúng đắn của dữ liệu.

