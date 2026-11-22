# Quyết định thông tin nào cần đồng bộ và mức độ trễ chấp nhận được

Khi các Bounded Context trao đổi dữ liệu, một quyết định quan trọng là **thông tin nào cần được chuyển sang context khác, chuyển vào thời điểm nào và consumer có thể sử dụng dữ liệu cũ đến mức nào**. Đồng bộ quá nhiều làm các context phụ thuộc chặt vào nhau và phải xử lý lượng dữ liệu lớn. Đồng bộ quá ít hoặc quá chậm có thể khiến một quyết định nghiệp vụ dựa trên dữ liệu lỗi thời.

Domain-Driven Design (DDD) khuyến khích mỗi Bounded Context sở hữu mô hình và dữ liệu mà nó chịu trách nhiệm. Consumer có thể giữ bản sao phục vụ đọc, nhưng bản sao không tự trở thành nguồn dữ liệu có thẩm quyền. Khi thiết kế đồng bộ, cần phân biệt dữ liệu tham khảo, dữ liệu snapshot tại thời điểm giao dịch và dữ liệu phải được xác nhận mới ngay lúc ra quyết định.

Bài học này giúp trả lời bốn câu hỏi:

1. Context nào là nguồn có thẩm quyền cho từng thông tin?
2. Consumer thực sự cần thuộc tính nào và cần dùng vào việc gì?
3. Thông tin phải mới đến mức nào tại thời điểm sử dụng?
4. Hệ thống xử lý ra sao khi dữ liệu đến chậm, bị lặp, sai thứ tự hoặc không đến?

## 1. Đồng bộ dữ liệu không đồng nghĩa với chia sẻ quyền sở hữu

Giả sử hệ thống thương mại điện tử có các context:

- **Customer Context** sở hữu hồ sơ khách hàng, thông tin liên hệ và phân hạng thành viên.
- **Catalog Context** sở hữu thông tin sản phẩm, mô tả và phân loại.
- **Pricing Context** sở hữu bảng giá, chương trình giảm giá và quy tắc tính giá.
- **Inventory Context** sở hữu số lượng có thể bán, lượng hàng giữ chỗ và vị trí kho.
- **Order Context** sở hữu đơn hàng và snapshot những điều kiện đã được chấp nhận khi đặt đơn.

Order Context có thể cần dữ liệu khách hàng, sản phẩm, giá và tồn kho. Điều đó không có nghĩa Order Context được quyền sửa hồ sơ khách hàng, thay giá catalog hoặc tự ghi giảm tồn kho. Nó chỉ cần dữ liệu hoặc kết quả từ context sở hữu tương ứng để hoàn thành use case.

~~~mermaid
flowchart LR
    Customer[Customer Context] -->|Customer profile event| Order[Order Context]
    Catalog[Catalog Context] -->|Product description event| Order
    Pricing[Pricing Context] -->|Price quote| Order
    Inventory[Inventory Context] <-->|Reservation command/result| Order
    Order -->|Order placed event| Billing[Billing Context]
~~~

Sơ đồ minh họa các luồng có thể có. Quan hệ thực tế cần được xác định theo nghiệp vụ, đặc biệt là bên nào sở hữu quyết định và dữ liệu. Không phải mọi mũi tên đều cần là một bản sao dữ liệu liên tục.

### Xác định nguồn có thẩm quyền theo từng thuộc tính

Không nên chỉ hỏi “context nào sở hữu Customer?” mà cần hỏi cụ thể “context nào có quyền quyết định email đã xác minh?”, “context nào sở hữu địa chỉ giao hàng đã chọn cho đơn?” hoặc “context nào có quyền xác nhận khoản tín dụng còn khả dụng?”.

| Thông tin | Nguồn có thẩm quyền thường gặp | Consumer có thể lưu gì? |
|---|---|---|
| Tên và hồ sơ liên hệ khách hàng | Customer Context | Bản sao đọc để hiển thị hoặc tìm kiếm |
| Trạng thái xác minh email | Customer/Identity Context theo phân chia hệ thống | Trạng thái gần nhất kèm thời điểm hoặc phiên bản |
| Mô tả và hình ảnh sản phẩm | Catalog Context | Projection cho danh sách sản phẩm |
| Giá bán đang áp dụng | Pricing Context | Cache có thời hạn hoặc quote được xác nhận |
| Giá đã chấp thuận trên đơn | Order Context sau khi đặt | Snapshot bất biến của giao dịch |
| Tồn kho có thể giữ | Inventory Context | Projection để tham khảo; quyết định giữ hàng vẫn do Inventory xác nhận |
| Trạng thái đơn hàng | Order Context | Bản sao trạng thái cho Billing, Shipping hoặc màn hình |
| Số tiền đã thu | Payment Context | Thông tin thanh toán được công bố; consumer không tự sửa ledger |

Nguồn có thẩm quyền có thể khác nhau theo bounded context và quy trình. Ví dụ, Customer Context sở hữu địa chỉ mặc định của khách hàng, nhưng khi khách chọn một địa chỉ giao hàng cho đơn, Order Context cần lưu snapshot địa chỉ đã được xác nhận cho đơn đó. Nếu khách đổi địa chỉ hồ sơ sau này, đơn đã đặt không nên tự thay đổi theo.

### Không tạo hai nguồn ghi cho cùng một sự thật

Nếu cả Order Context và Customer Context đều được phép chỉnh sửa cùng một email khách hàng, hệ thống không còn một nơi rõ ràng để phân xử khi hai giá trị khác nhau. Một bản sao ở consumer nên được cập nhật từ nguồn có thẩm quyền, hoặc được đánh dấu là snapshot theo thời điểm.

Một quy tắc thực hành:

- Một thuộc tính nghiệp vụ có một owner chịu trách nhiệm cho quyết định ghi.
- Consumer chỉ giữ bản sao phục vụ mục đích đã xác định.
- Nếu consumer cần yêu cầu thay đổi, nó gửi command hoặc gọi hợp đồng của owner.
- Không dùng đồng bộ hai chiều tùy tiện để “cập nhật cho giống nhau”.

## 2. Bắt đầu từ use case, không bắt đầu từ danh sách bảng

Cùng một thông tin có thể cần mức độ mới khác nhau tùy use case.

Ví dụ, số lượng tồn kho:

- Trang danh mục cần con số gần đúng để khách tham khảo.
- Giỏ hàng có thể cần cảnh báo nếu hàng đang khan hiếm.
- Bước xác nhận đơn cần biết có thể giữ đủ số lượng hay không.
- Báo cáo cuối ngày có thể chấp nhận dữ liệu chậm hơn nhiều.

Không thể đặt một SLA duy nhất cho “tồn kho” mà bỏ qua mục đích sử dụng.

### Xác định quyết định mà dữ liệu hỗ trợ

Với mỗi thông tin cần đồng bộ, hãy viết thành câu:

> Consumer dùng thông tin X để đưa ra quyết định Y tại thời điểm Z. Nếu thông tin cũ hơn ngưỡng T, hậu quả nghiệp vụ là gì?

Ví dụ:

> Order Context dùng trạng thái xác minh địa chỉ để quyết định có cho phép tạo nhãn giao hàng hay không. Nếu trạng thái cũ, đơn có thể bị gửi đến địa chỉ không còn hợp lệ.

Câu hỏi này giúp xác định liệu một bản sao cập nhật định kỳ có đủ hay cần xác nhận mới từ nguồn có thẩm quyền.

### Phân loại theo tác động khi dữ liệu cũ

| Tình huống | Tác động của dữ liệu cũ | Hướng thiết kế thường phù hợp |
|---|---|---|
| Tên sản phẩm trên trang danh mục | Thường chỉ ảnh hưởng hiển thị | Projection/cache cập nhật bất đồng bộ |
| Số lượt xem sản phẩm | Báo cáo có thể trễ | Batch hoặc stream aggregation |
| Giá hiển thị trong kết quả tìm kiếm | Có thể hiển thị giá chưa cập nhật | Projection có timestamp; xác nhận quote khi checkout |
| Giá đã chốt trong đơn | Không được tự đổi theo giá hiện tại | Snapshot trong Order |
| Tồn kho hiển thị | Có thể sai trong thời gian ngắn | Projection gần thời gian thực và thông báo còn hàng mang tính tham khảo |
| Giữ hàng khi đặt đơn | Có thể bán vượt tồn kho nếu chỉ dựa vào bản sao | Command tới Inventory để reserve nguyên tử |
| Hạn mức tín dụng khi phê duyệt giao dịch | Có thể gây rủi ro tài chính | Kiểm tra có thẩm quyền hoặc cơ chế reservation/ledger |
| Số liệu doanh thu phân tích | Thường không cần đồng bộ tức thời | Pipeline bất đồng bộ và đối soát |

Bảng chỉ đưa ra hướng thiết kế phổ biến. Mức độ rủi ro và quy định của từng doanh nghiệp quyết định lựa chọn cuối cùng.

## 3. Freshness và latency là hai khái niệm liên quan nhưng khác nhau

### Latency: mất bao lâu để thông tin đến consumer?

Latency là khoảng thời gian từ một mốc phát sinh ở producer đến một mốc quan sát ở consumer. Cần xác định rõ hai mốc:

- Thời điểm nghiệp vụ xảy ra.
- Thời điểm producer ghi nhận hoặc commit sự kiện.
- Thời điểm event được publish.
- Thời điểm consumer nhận.
- Thời điểm projection được cập nhật và sẵn sàng đọc.

Ví dụ, một sản phẩm được đổi giá lúc 10:00. Producer commit lúc 10:00:01, outbox relay publish lúc 10:00:02, consumer nhận lúc 10:00:03 và projection cập nhật lúc 10:00:04. End-to-end propagation latency tới projection là khoảng 3 giây nếu tính từ commit.

### Freshness: dữ liệu consumer đang dùng cũ đến mức nào?

Freshness mô tả độ mới của dữ liệu tại thời điểm consumer sử dụng. Một projection được cập nhật cách đây 2 giây có thể vẫn cũ nếu producer đã có một thay đổi mới hơn nhưng event đó đang bị kẹt.

Một cách định nghĩa đơn giản:

**Staleness = decision time − source effective time**

Trong đó:

- **Decision time** là thời điểm consumer dùng dữ liệu để quyết định.
- **Source effective time** là thời điểm phiên bản dữ liệu đang dùng có hiệu lực tại nguồn theo quy ước nghiệp vụ.

Nếu consumer cần dữ liệu có độ cũ tối đa 10 giây, điều kiện là staleness không vượt quá 10 giây tại thời điểm quyết định. Chỉ đo thời gian message đi qua broker là chưa đủ; cần biết projection có đang bắt kịp nguồn hay không.

### Phân biệt các mốc thời gian trong event

Một envelope có thể ghi:

~~~json
{
  "eventId": "evt-100",
  "occurredAt": "2026-11-18T10:00:00Z",
  "recordedAt": "2026-11-18T10:00:01Z",
  "publishedAt": "2026-11-18T10:00:02Z"
}
~~~

- **occurredAt**: sự việc xảy ra theo thời gian nghiệp vụ.
- **recordedAt**: producer ghi nhận hoặc commit sự kiện.
- **publishedAt**: relay hoặc producer đưa message ra kênh tích hợp.

Consumer có thể bổ sung receivedAt và processedAt trong telemetry riêng. Không nên lấy thời gian nhận message làm thời gian nghiệp vụ xảy ra.

Đồng hồ giữa các máy có thể lệch. Nếu đo latency giữa nhiều service, cần đồng bộ thời gian hệ thống và ưu tiên sequence/version của aggregate để xác định thứ tự thay đổi. Timestamp hữu ích cho quan sát, nhưng không phải lúc nào cũng đủ để phân xử thứ tự.

## 4. Xác định Freshness Budget cho từng use case

**Freshness budget** là mức độ cũ tối đa mà nghiệp vụ có thể chấp nhận cho một thông tin trong một quyết định cụ thể. Budget cần xuất phát từ hậu quả khi dữ liệu cũ, không chỉ từ khả năng kỹ thuật của broker.

Ví dụ minh họa:

| Use case | Thông tin | Freshness budget minh họa | Cách xử lý khi vượt budget |
|---|---|---:|---|
| Trang tìm kiếm sản phẩm | Mô tả, ảnh | 5 phút | Tiếp tục hiển thị và cập nhật nền |
| Trang sản phẩm | Giá tham khảo | 30 giây | Hiển thị thời điểm cập nhật; xác nhận lại khi checkout |
| Checkout | Giá quote | Theo thời hạn quote | Yêu cầu quote mới nếu hết hạn |
| Checkout | Tồn kho | Không dựa vào projection cũ để giữ hàng | Gửi reserve command đến Inventory |
| Dashboard vận hành | Trạng thái đơn | 1 phút | Hiển thị dấu hiệu dữ liệu đang cập nhật |
| Báo cáo tài chính | Giao dịch đã quyết toán | Theo lịch chốt và đối soát | Đánh dấu kỳ chưa hoàn tất, không coi dữ liệu tạm là cuối cùng |

Các con số chỉ là ví dụ để minh họa cách thảo luận. Đội nghiệp vụ phải xác nhận budget thực tế theo loại sản phẩm, rủi ro, SLA khách hàng và nghĩa vụ tài chính.

### Tách latency mục tiêu và freshness tối đa

Có thể đặt hai loại mục tiêu:

- **Propagation SLO:** ví dụ 99% sự kiện cập nhật projection trong vòng 5 giây kể từ khi producer commit.
- **Decision freshness limit:** dữ liệu không được quá 30 giây khi dùng để hiển thị giá tham khảo.

Hai con số không nhất thiết bằng nhau. Một hệ thống có thể thường xuyên cập nhật trong 2 giây nhưng khi broker lỗi, projection cũ đến 10 phút. Consumer cần biết giới hạn và hành vi khi vượt giới hạn.

Nên đo percentile như p50, p95 và p99 thay vì chỉ nhìn trung bình. Một trung bình 2 giây có thể che giấu một nhóm event bị trễ nhiều phút.

### Ngân sách trễ end-to-end

Tổng độ trễ có thể đến từ nhiều bước:

**L_total = L_commit-to-outbox + L_relay + L_broker + L_consumer + L_projection**

Đây là cách phân rã để quan sát. Thực tế có thể có retry, batch window, network và backpressure. Nếu budget là 5 giây, không thể dành 5 giây cho riêng broker rồi bỏ qua thời gian xử lý ở consumer.

## 5. Chọn đồng bộ đồng bộ hay bất đồng bộ

### Synchronous request/response

Consumer gọi provider và chờ kết quả trước khi tiếp tục.

~~~mermaid
sequenceDiagram
    participant O as Order Context
    participant P as Pricing Context
    O->>P: RequestPriceQuote(product, quantity)
    P-->>O: PriceQuote + validUntil
    O->>O: Validate quote and create order
~~~

Phù hợp khi:

- Use case cần câu trả lời có thẩm quyền ngay lúc ra quyết định.
- Kết quả không thể suy ra an toàn từ một bản sao cũ.
- Độ trễ và khả năng sẵn sàng của provider đáp ứng yêu cầu của luồng gọi.
- Số lượng dependency đồng bộ được giới hạn và có timeout rõ.

Rủi ro:

- Provider chậm làm consumer chậm.
- Provider lỗi có thể làm use case không hoàn thành.
- Gọi nhiều provider nối tiếp hoặc song song tạo fan-out và tăng xác suất thất bại.
- Nếu provider thực hiện side effect, retry có thể gây hành động trùng nếu không có idempotency.

Khi gọi API, cần timeout, retry có giới hạn, circuit breaker hoặc fallback theo mức rủi ro. Fallback không phải lúc nào cũng được phép: nếu không thể xác nhận hạn mức tín dụng, hệ thống có thể phải từ chối hoặc chuyển sang xử lý thủ công thay vì mặc định cho phép.

### Asynchronous event/message

Producer ghi nhận sự kiện, consumer xử lý sau.

~~~mermaid
sequenceDiagram
    participant C as Catalog Context
    participant B as Broker
    participant S as Search Context
    C->>C: Commit product change
    C->>B: Publish ProductUpdated
    B-->>S: Deliver event
    S->>S: Update search projection
~~~

Phù hợp khi:

- Consumer chỉ cần cập nhật bản sao hoặc phản ứng sau sự kiện.
- Có thể chấp nhận eventual consistency.
- Muốn tách thời gian hoạt động và tải giữa các context.
- Consumer cần xử lý độc lập, retry hoặc mở rộng theo tải.

Rủi ro:

- Dữ liệu không cập nhật ngay.
- Message có thể đến lặp hoặc sai thứ tự.
- Consumer có thể ngừng hoạt động và tích lũy backlog.
- Cần theo dõi dead-letter, replay và reconciliation.

### Kết hợp hai cách

Một use case thường dùng cả hai:

1. Checkout gọi Pricing để lấy quote có hiệu lực.
2. Checkout gửi command tới Inventory để giữ hàng.
3. Order Context lưu đơn và snapshot giá đã chấp thuận.
4. Sau commit, OrderPlaced được phát qua outbox.
5. Billing và Shipping cập nhật quy trình của chúng bất đồng bộ.

Đồng bộ ở bước cần xác nhận quyết định; bất đồng bộ cho các phản ứng có thể hoàn thành sau. Đây là một cách phân chia phổ biến, không phải quy tắc cứng.

## 6. Phân loại dữ liệu trước khi đồng bộ

### Reference data

Reference data là dữ liệu dùng để nhận diện hoặc diễn giải khái niệm, ví dụ danh mục quốc gia, loại sản phẩm hoặc mã đơn vị đo. Nó có thể được đồng bộ theo lịch hoặc qua event khi thay đổi.

Cần xác định:

- Mã nào là ổn định và có ý nghĩa trong phạm vi nào.
- Bên nào quản lý việc thêm, đổi tên hoặc ngừng sử dụng mã.
- Consumer xử lý mã mới chưa biết ra sao.
- Có cần giữ bản dịch hoặc nhãn hiển thị theo ngôn ngữ không.

Nếu một mã đã được dùng trong giao dịch lịch sử, không nên xóa hoặc tái sử dụng mã đó cho ý nghĩa khác.

### Master/reference profile data

Dữ liệu hồ sơ như tên, địa chỉ liên hệ hoặc phân hạng khách hàng thường có một context sở hữu. Consumer có thể giữ projection để đọc nhanh, nhưng phải biết projection có thể trễ và cần lấy lại dữ liệu khi quyết định đòi hỏi thông tin mới.

Không nên phát mọi field của hồ sơ đến mọi context. Hãy giới hạn theo mục đích và quyền truy cập. Dữ liệu cá nhân cần được bảo vệ, chỉ chia sẻ thuộc tính cần thiết và có quy trình cập nhật/xóa theo chính sách lưu giữ.

### Transaction snapshot

Snapshot là các giá trị cần giữ nguyên theo thời điểm một giao dịch được xác nhận. Ví dụ:

- Tên và mã sản phẩm đã bán.
- Đơn giá và loại tiền đã chấp thuận.
- Địa chỉ giao hàng đã chọn.
- Thuế suất hoặc điều kiện giảm giá được áp dụng.
- Tên pháp lý hoặc thông tin xuất hóa đơn đã được xác nhận.

Snapshot không có nghĩa là copy toàn bộ hồ sơ nguồn. Chỉ lưu những giá trị cần thiết để giải thích giao dịch về sau. Khi nguồn thay đổi, snapshot lịch sử không tự cập nhật.

### Operational state

Operational state là trạng thái thay đổi thường xuyên và có thể ảnh hưởng đến quyết định vận hành, ví dụ tồn kho, trạng thái giữ chỗ, hạn mức còn lại hoặc trạng thái giao hàng.

Với loại dữ liệu này, phải xác định rõ consumer cần bản sao để quan sát hay cần một quyết định có thẩm quyền. Một projection tồn kho có thể phục vụ hiển thị, nhưng lệnh giữ hàng vẫn cần được Inventory xử lý theo cơ chế nguyên tử.

### Analytical data

Dữ liệu phân tích thường tổng hợp từ nhiều context. Pipeline có thể dùng event stream, CDC hoặc batch ETL. Mức trễ chấp nhận được phụ thuộc vào câu hỏi kinh doanh: dashboard vận hành có thể cần gần thời gian thực, trong khi báo cáo tài chính chỉ được chốt sau đối soát.

Không dùng số liệu phân tích chưa hoàn tất như số liệu đã quyết toán. Hãy thể hiện kỳ dữ liệu, thời điểm cập nhật và trạng thái hoàn tất của pipeline.

## 7. Chọn cách đồng bộ phù hợp

| Cơ chế | Cách hoạt động | Phù hợp khi | Điểm cần lưu ý |
|---|---|---|---|
| API request/response | Consumer truy vấn provider | Cần câu trả lời mới hoặc có thẩm quyền | Timeout, availability, fan-out |
| Domain/Integration Event | Producer phát sự kiện sau thay đổi | Consumer cần phản ứng hoặc cập nhật projection | Duplicate, ordering, eventual consistency |
| Polling | Consumer định kỳ hỏi thay đổi | Nguồn không hỗ trợ push hoặc tải thấp | Độ trễ phụ thuộc chu kỳ, truy vấn lặp |
| Change Data Capture (CDC) | Đọc thay đổi từ log database | Đồng bộ dữ liệu kỹ thuật hoặc pipeline dữ liệu | Gắn với schema/storage, không tự mang đủ ngữ nghĩa miền |
| Batch/ETL | Chuyển dữ liệu theo lô | Báo cáo, đối soát, reference data ít đổi | Có cửa sổ dữ liệu cũ và cần kiểm soát lần chạy |
| Shared database | Nhiều context truy cập cùng kho dữ liệu | Chỉ trong trường hợp ràng buộc kiến trúc được chấp nhận rõ | Dễ phá ownership và tạo phụ thuộc schema |

### API không nên trở thành cách đọc mọi thứ

Nếu mỗi request của Order Context gọi Customer, Catalog, Pricing, Inventory, Tax và Shipping để dựng màn hình, một dependency chậm có thể làm toàn bộ màn hình chậm. Cần xem xét projection/read model hoặc API tổng hợp có trách nhiệm rõ ràng.

Tuy nhiên, projection chỉ là bản sao. Khi cần xác nhận giá hoặc giữ hàng, use case vẫn gọi owner có thẩm quyền.

### Event không phải là đồng bộ mọi field

Một event như ProductUpdated không nhất thiết phải mang toàn bộ Product. Có thể phát các sự kiện cụ thể như ProductDescriptionChanged, ProductDiscontinued hoặc ProductCategoryAssigned. Consumer chỉ nhận những gì nó cần và có thể xây projection riêng.

Nếu một consumer cần trạng thái hiện tại đầy đủ sau khi nhận event, có thể dùng event để biết thay đổi rồi gọi API đọc, hoặc phát một snapshot event được thiết kế có chủ đích. Chọn cách nào tùy volume, latency và khả năng sẵn sàng.

### CDC là cơ chế kỹ thuật, không tự thay thế hợp đồng miền

CDC có thể đọc row change từ database log và đưa sang hệ thống khác. Nó hữu ích cho data warehouse hoặc đồng bộ kỹ thuật, nhưng một row update không nhất thiết biểu đạt ý nghĩa nghiệp vụ.

Ví dụ, một transaction có thể cập nhật ba bảng cho cùng một hành động đặt đơn. Consumer đọc từng row change có thể thấy trạng thái trung gian hoặc phụ thuộc vào schema nội bộ. Nếu context khác cần hiểu “đơn đã được đặt”, integration event có ngữ nghĩa rõ thường phù hợp hơn.

## 8. Thiết kế projection và bản sao có kiểm soát

Một consumer có thể duy trì read model riêng:

~~~text
Catalog Context
    |
    | ProductPublished / ProductDescriptionChanged
    v
Search Context
    |
    v
SearchProductProjection
  - productId
  - displayName
  - category
  - thumbnail
  - sourceVersion
  - updatedAt
~~~

Projection được tối ưu theo truy vấn của Search Context. Nó không có quyền sửa catalog. Nếu event bị mất hoặc consumer lỗi, projection có thể được rebuild từ snapshot/API hoặc từ event history nếu hệ thống có lưu giữ phù hợp.

### Lưu dấu freshness trong projection

Một projection có thể giữ:

- sourceVersion: phiên bản nguồn cuối cùng đã áp dụng.
- sourceUpdatedAt: thời điểm dữ liệu có hiệu lực ở nguồn.
- processedAt: thời điểm consumer cập nhật projection.
- eventId: event cuối cùng được áp dụng nếu cần truy vết.

Những trường này hỗ trợ trả lời “dữ liệu đang hiển thị được cập nhật từ nguồn nào và khi nào?”. Chúng không thay thế cơ chế version/sequence để xử lý thứ tự.

### Không dùng thời điểm nhận làm thứ tự duy nhất

Hai event có thể đến sai thứ tự do retry hoặc partition. Nếu Product version 12 đến trước version 11, consumer không nên ghi đè projection mới bằng dữ liệu cũ.

~~~java
public void apply(ProductUpdated event) {
    ProductProjection current = repository.find(event.productId())
            .orElse(null);

    if (current != null && event.aggregateVersion() <= current.sourceVersion()) {
        return; // Bỏ qua event cũ hoặc đã áp dụng.
    }

    repository.save(ProductProjection.from(event));
}
~~~

Đoạn code giả định version tăng đơn điệu trong phạm vi một Product và việc kiểm tra/cập nhật được thực hiện nguyên tử. Nếu nhiều consumer xử lý đồng thời cùng product, cần optimistic locking hoặc upsert có điều kiện ở database để tránh race giữa bước đọc và ghi.

## 9. Snapshot và dữ liệu tham chiếu cần được phân biệt

Một đơn hàng đã đặt thường cần giữ snapshot giá, mô tả sản phẩm hoặc địa chỉ đã xác nhận. Nếu chỉ giữ ProductId và mỗi lần hiển thị lại truy vấn catalog hiện tại, hóa đơn cũ có thể hiển thị giá hoặc tên mới không đúng với giao dịch lúc đặt.

| Nhu cầu | Lưu ID | Lưu snapshot | Truy vấn nguồn khi đọc |
|---|---:|---:|---:|
| Biết sản phẩm nguồn nào được đặt | Có | Không bắt buộc | Không |
| Hiển thị tên sản phẩm tại thời điểm mua | Có thể | Có | Không |
| Hiển thị mô tả mới nhất của sản phẩm | Có | Không | Có hoặc dùng projection |
| Tính lại giá hiện tại cho một báo giá mới | Có | Không dùng snapshot cũ làm giá hiện hành | Có quote mới |
| Giải thích giá đã chốt trong đơn cũ | Có | Có | Không cần thay đổi snapshot |
| Biết trạng thái hiện tại của sản phẩm | Có | Snapshot cũ không đủ | Có hoặc projection có freshness |

Đừng snapshot tất cả chỉ để tránh gọi API. Snapshot có chi phí lưu trữ, cập nhật và bảo vệ dữ liệu. Hãy lưu khi nghiệp vụ cần bảo toàn sự thật tại thời điểm giao dịch.

## 10. Eventual Consistency và cách giải thích cho nghiệp vụ

Khi một context cập nhật và context khác nhận thay đổi sau, hệ thống có thể ở trạng thái chưa đồng nhất trong một khoảng thời gian. Đây là **eventual consistency**: nếu không còn thay đổi mới và thông điệp được xử lý thành công, bản sao sẽ hội tụ về trạng thái nguồn.

Eventual consistency không có nghĩa “dữ liệu sẽ tự đúng ngay”. Hệ thống cần:

- Đảm bảo thay đổi được ghi nhận để có thể phát lại.
- Retry khi lỗi tạm thời.
- Theo dõi backlog và thời gian xử lý.
- Xử lý message lặp an toàn.
- Phát hiện event bị bỏ sót hoặc sai thứ tự.
- Có quy trình đối soát và sửa projection.

### Ví dụ: trạng thái đơn và trạng thái thanh toán

Order Context phát OrderPlaced. Billing nhận event sau vài giây và tạo invoice. Trong khoảng chờ, Order đã ở trạng thái PLACED nhưng Billing chưa có invoice.

Đây không nhất thiết là lỗi nếu nghiệp vụ chấp nhận độ trễ. Giao diện có thể hiển thị “Đang khởi tạo hóa đơn”. Nếu khách cần tải hóa đơn ngay lập tức, yêu cầu đó có thể buộc hệ thống dùng đồng bộ hoặc trả trạng thái chờ rõ ràng.

### Trạng thái trung gian phải được mô hình hóa

Thay vì giả định mọi thao tác hoàn tất tức thì, có thể có trạng thái:

- PENDING: đã yêu cầu nhưng chưa có kết quả.
- PROCESSING: consumer đang xử lý.
- CONFIRMED: kết quả đã được xác nhận.
- REJECTED: bị từ chối.
- FAILED_RETRYABLE: lỗi có thể thử lại.
- FAILED_FINAL: lỗi không thể tự phục hồi.

Tên và số lượng trạng thái cần phản ánh nghiệp vụ. Không nên để trạng thái kỹ thuật tràn vào domain model nếu nó chỉ là chi tiết vận hành của consumer.

## 11. Quyết định khi dữ liệu vượt freshness budget

Consumer cần hành vi rõ khi dữ liệu quá cũ. Có thể chọn một trong các cách sau:

| Cách xử lý | Mô tả | Khi phù hợp |
|---|---|---|
| Continue with stale data | Tiếp tục nhưng ghi rõ thời điểm dữ liệu | Nội dung tham khảo, dashboard |
| Refresh before use | Gọi nguồn có thẩm quyền để lấy mới | Giá quote, trạng thái xác minh |
| Reject/defer decision | Từ chối hoặc chuyển sang pending | Quyết định rủi ro cao, chưa xác nhận được |
| Use a reservation/lease | Owner cấp quyền tạm thời có thời hạn | Tồn kho, hạn mức hoặc tài nguyên khan hiếm |
| Manual review | Chuyển cho người có thẩm quyền | Rủi ro cao hoặc hệ thống nguồn đang lỗi |

Không có fallback chung cho mọi loại dữ liệu. Ví dụ, hiển thị tên sản phẩm cũ thường chấp nhận được; cho phép giao dịch tín dụng khi không xác nhận được hạn mức có thể không được phép.

### Quote và reservation có thời hạn

Thay vì sao chép giá hoặc tồn kho rồi tin vào bản sao, owner có thể cấp một quyền sử dụng có thời hạn:

- Pricing cấp PriceQuote với quoteId, giá, currency và validUntil.
- Inventory cấp StockReservation với reservationId, số lượng và expiresAt.

Consumer có thể sử dụng kết quả trong thời hạn đã cam kết. Sau thời hạn, cần xác nhận hoặc tạo reservation/quote mới. Đây là cách chuyển câu hỏi “bản sao cũ bao lâu?” thành một hợp đồng có thời hạn rõ ràng.

## 12. Đồng bộ không đảm bảo tính nhất quán xuyên nhiều Aggregate

Một hệ thống có thể đồng bộ dữ liệu rất nhanh nhưng vẫn không có một giao dịch nguyên tử giữa nhiều context. Event đến sau vài mili giây vẫn là bất đồng bộ; consumer có thể lỗi sau khi producer đã commit.

Nếu quy trình gồm nhiều bước như đặt đơn, giữ hàng, thu tiền và giao hàng, hãy thiết kế quy trình phối hợp:

~~~mermaid
flowchart TD
    A[Order Placed] --> B[Request Stock Reservation]
    B --> C{Inventory result}
    C -->|Reserved| D[Request Payment]
    C -->|Rejected| X[Cancel Order]
    D --> E{Payment result}
    E -->|Authorized| F[Confirm Order]
    E -->|Declined| G[Release Stock]
    G --> X
~~~

Một Process Manager hoặc Saga theo dõi tiến trình và hành động bù trừ. Việc giữ hàng, thu tiền và hủy đơn là các quyết định ở các context có ownership riêng. Không nên giả định một transaction phân tán sẽ làm mọi thứ cùng commit trừ khi kiến trúc thực sự hỗ trợ và doanh nghiệp chấp nhận chi phí đó.

### Phân biệt consistency requirement với propagation speed

Nếu nghiệp vụ yêu cầu “không bán vượt tồn kho”, điều quan trọng là thao tác reserve phải được Inventory bảo vệ nguyên tử. Làm projection cập nhật trong 100 ms không thay thế được cơ chế reserve. Tốc độ đồng bộ cao không tự tạo ra consistency guarantee.

Ngược lại, nếu nghiệp vụ chỉ cần “trang tìm kiếm hiển thị số lượng gần đúng”, projection cập nhật sau 10 giây có thể đủ. Đừng dùng distributed lock hoặc synchronous fan-out cho một màn hình không cần mức bảo đảm đó.

## 13. Xử lý message lặp, sai thứ tự và mất message

### Idempotency

Broker thường có thể giao message nhiều lần. Consumer cần thiết kế thao tác sao cho xử lý lại cùng một event không tạo thêm tác dụng phụ.

~~~java
@Transactional
public void handle(OrderPlaced event) {
    if (processedEventRepository.exists(event.eventId())) {
        return;
    }

    billingService.createInvoiceIfAbsent(event.orderId());
    processedEventRepository.record(event.eventId());
}
~~~

Đoạn code minh họa ý tưởng. Việc kiểm tra event đã xử lý, tạo invoice và ghi dấu phải được bảo vệ bởi transaction/unique constraint phù hợp. Nếu tác dụng phụ nằm ở hệ thống ngoài, cần idempotency key ở API đích hoặc một quy trình đối soát; chỉ ghi event ID trong DB local không đủ bảo đảm side effect bên ngoài không bị lặp.

### Ordering

Nếu các event của cùng aggregate cần đúng thứ tự, có thể dùng aggregate ID làm partition key và mang theo aggregate version/sequence. Consumer cần xác định:

- Có bỏ qua event cũ không?
- Nếu thiếu sequence ở giữa thì chờ, retry hay tải snapshot mới?
- Event đến muộn có thể được xử lý độc lập không?
- Có cần xử lý tuần tự cho từng aggregate không?

Không nên yêu cầu thứ tự toàn cục nếu nghiệp vụ chỉ cần thứ tự trong phạm vi một aggregate.

### Outbox, retry và dead-letter

Producer nên ghi thay đổi aggregate và outbox record trong cùng transaction. Relay gửi outbox đến broker và có thể retry. Consumer lỗi tạm thời có thể retry với backoff; lỗi không thể xử lý sau số lần cho phép có thể chuyển dead-letter để điều tra.

Dead-letter không phải nơi kết thúc trách nhiệm. Cần có owner, cảnh báo, công cụ xem payload an toàn và quy trình replay sau khi sửa lỗi. Trước khi replay, phải hiểu liệu một phần tác dụng phụ đã xảy ra hay chưa.

## 14. Reconciliation: kiểm tra bản sao có hội tụ không

Event-driven synchronization cần một cách phát hiện sai lệch ngoài luồng event thông thường. Reconciliation so sánh dữ liệu consumer với nguồn có thẩm quyền hoặc với một checkpoint được tin cậy.

Ví dụ:

- Mỗi ngày so sánh số đơn Order Context đã đặt với số invoice Billing đã tạo.
- Kiểm tra projection của Catalog có sourceVersion thấp hơn version hiện tại quá lâu.
- Đối soát reservation đã hết hạn nhưng Order vẫn ở trạng thái chờ.
- Phát hiện message nằm trong dead-letter queue quá thời hạn.

Reconciliation có thể thực hiện bằng API, batch export, CDC hoặc báo cáo đối soát. Kết quả cần phân loại:

- Thiếu dữ liệu ở consumer.
- Dữ liệu consumer cũ hơn nguồn.
- Dữ liệu không khớp semantics hoặc mapping.
- Sự kiện bị xử lý lặp.
- Quy trình nghiệp vụ đang ở trạng thái trung gian hợp lệ.

Không phải mọi chênh lệch đều là lỗi. Ví dụ Order đã đặt nhưng Billing chưa tạo invoice trong khoảng thời gian xử lý cho phép có thể là trạng thái pending hợp lệ. Reconciliation phải hiểu trạng thái và freshness budget để tránh báo động giả.

## 15. Quan sát freshness và độ trễ trong vận hành

Để biết đồng bộ có đáp ứng cam kết hay không, nên theo dõi:

| Metric | Ý nghĩa |
|---|---|
| Event propagation latency | Thời gian từ producer commit đến consumer xử lý xong |
| Projection freshness age | Tuổi dữ liệu nguồn cuối cùng đã áp dụng |
| Consumer lag/backlog | Số message hoặc thời gian consumer đang tụt lại |
| Retry count | Số lần xử lý lại |
| Dead-letter count | Số event không thể xử lý tự động |
| Reconciliation mismatch | Số bản ghi hoặc tổng hợp không khớp |
| Outbox oldest age | Tuổi bản ghi outbox chưa gửi lâu nhất |

Nên gắn correlation ID, event ID, aggregate ID và source version vào trace/log theo chính sách dữ liệu. Tránh ghi payload chứa thông tin cá nhân hoặc bí mật vào log chỉ để tiện debug.

Đặt cảnh báo theo ngưỡng nghiệp vụ, ví dụ projection giá tham khảo trễ hơn budget, hoặc invoice chưa được tạo sau SLA. Không nên chỉ cảnh báo khi broker CPU cao; broker khỏe không có nghĩa dữ liệu đã hội tụ.

## 16. Ví dụ thiết kế end-to-end: đặt hàng với giá và tồn kho

### Yêu cầu nghiệp vụ

Khách đặt 2 sản phẩm. Hệ thống cần:

- Giá có hiệu lực tại thời điểm checkout.
- Không bán vượt số lượng có thể giữ.
- Lưu giá và mô tả đã chấp thuận trong đơn.
- Cho Billing và Shipping biết đơn đã được đặt.
- Cho phép các context xử lý tiếp sau khi Order commit.

### Luồng xử lý đề xuất

1. Search projection hiển thị sản phẩm, giá tham khảo và tồn kho gần nhất.
2. Khi checkout, Order application service yêu cầu Pricing cấp quote mới.
3. Order gửi command ReserveStock tới Inventory.
4. Inventory kiểm tra và giữ số lượng trong transaction của chính nó, trả reservation ID và thời hạn.
5. Order tạo aggregate với ProductId, snapshot tên, quote giá, reservation reference và địa chỉ giao hàng đã chọn.
6. Order đặt đơn và lưu aggregate cùng outbox record trong một transaction.
7. Relay phát OrderPlaced integration event.
8. Billing tạo invoice; Shipping bắt đầu chuẩn bị giao hàng.
9. Nếu bước sau thất bại, Process Manager/Saga áp dụng chính sách bù trừ, ví dụ giải phóng reservation hoặc yêu cầu hoàn tiền.

~~~mermaid
sequenceDiagram
    actor Buyer as Khách hàng
    participant O as Order Context
    participant P as Pricing Context
    participant I as Inventory Context
    participant DB as Order Database
    participant B as Broker
    participant F as Billing/Shipping

    Buyer->>O: Checkout
    O->>P: Request price quote
    P-->>O: Quote + validUntil
    O->>I: ReserveStock
    I-->>O: ReservationId + expiresAt
    O->>O: Build order with snapshots
    O->>DB: Save Order + Outbox
    DB-->>O: Commit
    DB->>B: Outbox relay publishes OrderPlaced
    B-->>F: Deliver integration event
    F->>F: Process independently
~~~

Luồng này không tạo một transaction duy nhất giữa Pricing, Inventory, Order, Billing và Shipping. Mỗi context bảo vệ quyết định và dữ liệu thuộc quyền sở hữu của mình. Quy trình tổng thể được phối hợp qua quote, reservation, event và các hành động bù trừ.

### Quyết định freshness cho từng loại thông tin

| Thông tin | Dùng ở bước nào? | Cách bảo đảm |
|---|---|---|
| Tên và ảnh sản phẩm | Tìm kiếm/xem chi tiết | Projection có thể trễ |
| Giá tham khảo | Trước checkout | Projection, hiển thị thời điểm cập nhật |
| Giá được chấp thuận | Checkout | Quote có hiệu lực và snapshot vào Order |
| Số lượng tồn kho tham khảo | Xem sản phẩm | Projection gần thời gian thực |
| Số lượng được giữ | Checkout | Inventory xác nhận reservation |
| Địa chỉ giao hàng đã chọn | Đặt đơn | Snapshot vào Order |
| Trạng thái invoice | Sau khi đặt | Event từ Billing và projection trong Order/read model nếu cần |

Bảng cho thấy cùng một domain có thể dùng nhiều chiến lược đồng bộ. Giá tham khảo không cần bảo đảm giống giá đã chốt; tồn kho hiển thị không có quyền thay thế reservation; địa chỉ lịch sử cần snapshot để giữ nguyên nội dung giao dịch.

## 17. Quy trình quyết định thông tin cần đồng bộ

Với mỗi thuộc tính hoặc sự kiện, có thể dùng quy trình sau:

1. **Xác định owner:** context nào có quyền tạo, sửa và xác nhận sự thật?
2. **Xác định consumer:** context nào cần thông tin và use case cụ thể là gì?
3. **Xác định mục đích:** hiển thị, tìm kiếm, quyết định, snapshot, vận hành hay phân tích?
4. **Tối thiểu hóa dữ liệu:** consumer cần field nào, có thể dùng ID hay cần snapshot?
5. **Đánh giá hậu quả của dữ liệu cũ:** điều gì xảy ra nếu dữ liệu chậm 1 giây, 30 giây hoặc 10 phút?
6. **Đặt freshness budget:** xác định giới hạn và tỷ lệ đáp ứng mong muốn theo use case.
7. **Chọn cơ chế:** API, event, polling, CDC hoặc batch.
8. **Chọn hành vi khi vượt budget:** tiếp tục, refresh, chờ, từ chối, reservation hoặc manual review.
9. **Thiết kế lỗi phân tán:** retry, idempotency, ordering, outbox, dead-letter và reconciliation.
10. **Đo lường:** metric, trace, cảnh báo và owner vận hành.

Một record quyết định đồng bộ có thể ghi:

| Trường | Nội dung cần ghi |
|---|---|
| Data item | Tên thuộc tính hoặc sự kiện |
| Source owner | Bounded Context có thẩm quyền |
| Consumer | Context nhận dữ liệu |
| Use case | Mục đích sử dụng |
| Data shape | ID, snapshot hoặc projection fields |
| Mechanism | API, event, polling, CDC, batch |
| Freshness budget | Độ cũ tối đa được chấp nhận |
| Failure behavior | Khi stale, unavailable hoặc message lỗi |
| Reconciliation | Cách phát hiện và sửa sai lệch |
| Contract owner | Người/nhóm chịu trách nhiệm hợp đồng |

## 18. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách điều chỉnh |
|---|---|---|
| Đồng bộ mọi field của mọi context | Tăng coupling, volume và rủi ro dữ liệu | Chỉ chuyển dữ liệu cần cho use case |
| Không xác định source of truth | Nhiều nơi ghi cùng một sự thật | Chỉ định owner theo từng thuộc tính |
| Dùng projection cũ để ra quyết định quan trọng | Chấp nhận giao dịch dựa trên dữ liệu lỗi thời | Gọi owner hoặc dùng reservation/quote |
| Đặt một SLA cho cả domain | Mức trễ không phù hợp với từng use case | Đặt freshness budget theo quyết định |
| Chỉ đo broker latency | Bỏ qua consumer lag và projection processing | Đo end-to-end tới thời điểm dữ liệu sẵn sàng |
| Cho rằng event delivery là exactly-once | Side effect có thể lặp | Consumer idempotent và có đối soát |
| Dùng timestamp làm thứ tự tuyệt đối | Clock skew và event đến muộn làm sai kết quả | Dùng aggregate version/sequence |
| Dùng CDC như business event | Consumer phụ thuộc schema và thay đổi bảng nội bộ | Công bố integration event có ngữ nghĩa |
| Không có dead-letter owner | Message lỗi nằm lại vô thời hạn | Cảnh báo, điều tra và replay có kiểm soát |
| Không có reconciliation | Projection sai lệch kéo dài mà không ai phát hiện | Đối soát theo nghiệp vụ và freshness budget |
| Dùng synchronous fan-out cho mọi dữ liệu | Tăng latency và giảm availability | Projection cho đọc; gọi owner chỉ khi cần xác nhận |
| Snapshot mọi dữ liệu nguồn | Dữ liệu trùng lặp và nghĩa vụ bảo vệ tăng | Chỉ snapshot giá trị cần giữ theo thời điểm |

## 19. Checklist rà soát đồng bộ

- [ ] Mỗi thuộc tính có source owner và quyền ghi rõ ràng.
- [ ] Consumer và use case sử dụng thông tin được xác định cụ thể.
- [ ] Đã phân biệt dữ liệu tham khảo, snapshot, operational state và analytical data.
- [ ] Payload chỉ chứa dữ liệu cần thiết, không sao chép toàn bộ aggregate.
- [ ] Đã xác định freshness budget theo hậu quả nghiệp vụ.
- [ ] Đã phân biệt propagation latency với freshness age.
- [ ] Đã chọn synchronous/asynchronous theo yêu cầu quyết định.
- [ ] Dữ liệu cũ vượt budget có hành vi rõ ràng.
- [ ] Quote/reservation có ID và thời hạn nếu nghiệp vụ cần.
- [ ] Producer ghi outbox cùng transaction khi cần phát event bền vững.
- [ ] Consumer idempotent và xử lý event sai thứ tự.
- [ ] Có retry, dead-letter, replay và owner vận hành.
- [ ] Có reconciliation để phát hiện sai lệch kéo dài.
- [ ] Metric đo end-to-end tới projection hoặc điểm sử dụng.
- [ ] Dữ liệu cá nhân được tối thiểu hóa và có chính sách lưu giữ.
- [ ] Mọi trạng thái pending/eventual consistency đều được diễn đạt rõ cho nghiệp vụ và người dùng.

## Kết luận

Quyết định đồng bộ phải bắt đầu từ quyền sở hữu dữ liệu và use case cần hỗ trợ. Mỗi context nên là nguồn có thẩm quyền cho sự thật mà nó quản lý; consumer chỉ giữ bản sao hoặc snapshot có mục đích. Freshness budget cần được đặt theo hậu quả khi dữ liệu cũ, sau đó mới chọn API đồng bộ, event bất đồng bộ, polling, CDC hay batch. Với dữ liệu quan trọng, projection nhanh không thay thế được xác nhận có thẩm quyền hoặc reservation nguyên tử. Outbox, idempotency, ordering, reconciliation và quan sát end-to-end giúp hệ thống xử lý được độ trễ thực tế mà vẫn giữ ranh giới trách nhiệm rõ ràng.

