# Nhất quán giữa các bản sao nghiệp vụ và giới hạn thời gian lệch

Trong ứng dụng dùng NoSQL, một sự thật nghiệp vụ thường xuất hiện ở nhiều nơi. Thông tin sản phẩm có thể được lưu trong **Product Store**, sao chép sang **Search Index** để tìm kiếm, lưu vào **cache** để hiển thị nhanh, xuất hiện trong **giỏ hàng** và đi vào **đơn hàng** khi khách xác nhận mua. Một thay đổi giá sản phẩm vì vậy có thể được nhìn thấy ở những bản sao vào **những thời điểm khác nhau**.

Đây là hệ quả tự nhiên của **quan hệ và lặp dữ liệu (denormalization)**: thay vì buộc mọi thao tác đọc phải truy cập nhiều kho và kết hợp dữ liệu tại thời điểm request, hệ thống giữ sẵn những **bản sao nghiệp vụ** được tối ưu theo từng đường truy vấn. Việc sao chép giúp đọc nhanh và phân tán tải, nhưng tạo ra trách nhiệm mới: phải biết **bản nào có thẩm quyền, bản nào được phép cũ, cũ tối đa bao lâu, đồng bộ bằng cách nào và làm gì khi vượt giới hạn**.

**Nhất quán giữa các bản sao nghiệp vụ** không có nghĩa mọi bản sao phải có cùng một giá trị ở mọi thời điểm. Có bản sao cần phản ánh trạng thái mới nhất, có bản sao cố ý lưu **ảnh chụp lịch sử bất biến**. Thiết kế đúng phải bắt đầu từ **ý nghĩa nghiệp vụ của từng bản sao**, rồi mới chọn kỹ thuật đồng bộ.

> Ví dụ xuyên suốt: một cửa hàng có sản phẩm **P-42**, tên “Bàn làm việc”, giá đang bán 1.500.000 VND. Người bán cập nhật giá thành 1.390.000 VND. Trang quản trị cần nhìn thấy ngay, tìm kiếm có thể trễ một chút, còn lúc thanh toán phải quyết định giá theo chính sách chốt giá của hệ thống. Các mốc độ trễ trong bài là **giả định minh họa**, không phải cam kết của MongoDB, Redis, Elasticsearch/OpenSearch, Cassandra hay một sản phẩm cụ thể.

## 1. Trước tiên: thế nào là một “bản sao nghiệp vụ”?

Một bản sao nghiệp vụ là dữ liệu mô tả cùng một thực thể hoặc cùng một sự thật, được lưu lại ở vị trí hoặc hình dạng khác để phục vụ một mục đích cụ thể. Nó có thể nằm trong cùng database, một collection khác, một cache, một chỉ mục tìm kiếm hoặc một dịch vụ độc lập.

| Bản lưu | Ví dụ | Mục tiêu | Có cần tự cập nhật khi nguồn thay đổi? |
| --- | --- | --- | --- |
| **Nguồn có thẩm quyền (source of truth)** | Product Store lưu giá hiện hành | Quyết định trạng thái đúng cho nghiệp vụ | Được cập nhật qua đường ghi có thẩm quyền |
| **Bản đọc dẫn xuất (read model/projection)** | Danh sách sản phẩm theo danh mục | Đọc theo truy vấn đã tối ưu | Có, theo hợp đồng độ mới |
| **Search index** | Tài liệu tìm kiếm tên, nhãn, giá | Tìm từ khóa, lọc, xếp hạng | Có, thường bất đồng bộ |
| **Cache** | product:P-42 trong Redis | Giảm độ trễ và tải nguồn | Có thể vô hiệu hóa/làm mới hoặc hết TTL |
| **Snapshot nghiệp vụ** | Tên, giá, thuế đã chốt trong order line | Giữ bằng chứng của giao dịch lịch sử | **Không** tự đổi theo catalog hiện tại |
| **Bản sao phân tích** | Doanh thu theo ngày/khu vực | Báo cáo, tổng hợp | Có thể trễ theo chu kỳ/stream |
| **Bản sao vận hành của database** | Replica để phục vụ sẵn sàng/đọc | Tăng độ bền và availability | Do cơ chế replication của engine quản lý |

**Phân biệt quan trọng:** bản đọc dẫn xuất, cache và snapshot đơn hàng không phải cùng một thứ. Nếu người bán sửa tên sản phẩm, search index nên được cập nhật; nhưng **tên sản phẩm ghi trong đơn hàng đã chốt thường phải được giữ nguyên**, vì đó là bằng chứng của thứ khách đã mua tại thời điểm giao dịch.

### 1.1. Cùng trường dữ liệu nhưng hai hợp đồng khác nhau

~~~json
{
  "productId": "P-42",
  "name": "Bàn làm việc",
  "priceMinor": 1390000,
  "currency": "VND",
  "version": 18
}
~~~

Đây là **trạng thái sản phẩm hiện hành**, ví dụ sau một lần thay đổi giá.

~~~json
{
  "orderId": "O-903",
  "lines": [
    {
      "productId": "P-42",
      "productNameSnapshot": "Bàn làm việc",
      "unitPriceMinorSnapshot": 1500000,
      "quantity": 1
    }
  ],
  "confirmedAt": "2026-11-13T10:00:00Z"
}
~~~

Đây là **snapshot đã chốt của đơn hôm trước**. Giá 1.500.000 VND **không bị sai** chỉ vì Product Store hiện có giá 1.390.000 VND. Quy tắc đúng là: dữ liệu snapshot khớp với **giao dịch đã xác nhận**, không bắt buộc khớp với trạng thái hiện tại.

Vì vậy, câu hỏi đầu tiên khi thấy hai bản ghi khác nhau không phải “tại sao chúng không đồng nhất?”, mà là **“hai bản ghi này có phải đại diện cho cùng một thời điểm và cùng một sự thật cần đồng nhất không?”**.

## 2. Xác định quyền sở hữu dữ liệu và đường cập nhật

Mỗi loại sự thật nên có một nơi **có quyền quyết định cuối cùng**. Những hệ khác có thể giữ bản dẫn xuất, nhưng không được tùy ý sửa rồi coi đó là nguồn chính.

Ví dụ về ma trận sở hữu:

| Sự thật nghiệp vụ | Nguồn có thẩm quyền | Bản sao phục vụ đọc | Hành động khi cần quyết định chính xác |
| --- | --- | --- | --- |
| Giá hiện hành của sản phẩm | Product Store | Search, cache, listing | Đọc/xác nhận giá tại luồng chốt đơn |
| Số hàng có thể cấp phát | Inventory Service/Store | Trang chi tiết, gợi ý “còn hàng” | Ghi giữ hàng có điều kiện ở Inventory |
| Trạng thái thanh toán | Payment Service/ledger | Order summary, dashboard | Đối chiếu payment reference tại nguồn |
| Tên hiển thị hiện tại của khách | Customer Profile | CRM search, autocomplete | Dùng hồ sơ nguồn khi cần thông tin mới nhất |
| Địa chỉ giao hàng đã xác nhận | Order snapshot | Trang lịch sử đơn | Giữ snapshot theo trạng thái đơn và quy trình sửa đơn |
| Quyền truy cập còn hiệu lực | Auth/Permission Store | Cache quyền nếu chính sách cho phép | Kiểm tra cơ chế thu hồi/quyền có thẩm quyền |

Việc **sở hữu dữ liệu** không đồng nghĩa mọi bản sao đều cần gọi nguồn trong mỗi lần đọc. Cần biết luồng nào có thể nhận dữ liệu cũ và luồng nào phải kiểm tra tại nguồn.

### 2.1. Viết rõ hướng đồng bộ

Một mô hình hướng dữ liệu phổ biến:

~~~mermaid
flowchart LR
    W["Lệnh cập nhật sản phẩm"] --> S[("Product Store\nNguồn chính")]
    S --> O[("Outbox / Change stream")]
    O --> C["Consumer / Projector"]
    C --> I[("Search index")]
    C --> R[("Product listing read model")]
    C --> K[("Cache invalidation / refresh")]
    Q["Checkout"] --> S
    H["Lịch sử đơn"] --> N[("Order snapshot\nBất biến theo giao dịch")]
~~~

Luồng trên minh họa **một nguồn có thẩm quyền** và nhiều bản dẫn xuất. Nếu ứng dụng cho cả Search Service, Product Service và Cart Service **tự chỉnh giá hiện hành rồi đồng bộ ngược nhau**, hệ thống phải giải quyết một bài toán xung đột đa nguồn khó hơn nhiều.

Khi có thể, hãy quy định:

- **Ai được ghi trường nào?**
- **Sự kiện nào biểu thị việc thay đổi đã được commit?**
- **Bản sao nào phải nhận sự kiện và thay đổi ra sao?**
- **Nếu bản sao bị chậm hoặc lỗi, ai phát hiện và sửa?**
- **Khi có hai phiên bản trái nhau, tiêu chí nào quyết định phiên bản thắng?**

## 3. Ba mức độ nhất quán thường phải phân biệt

### 3.1. Đọc nhất quán tại nguồn

Với một thao tác đòi hỏi đúng ngay tại thời điểm ra quyết định, ứng dụng dùng đường ghi/đọc có thẩm quyền cùng bảo đảm nhất quán phù hợp. Ví dụ, khi trừ một đơn vị hàng khỏi tồn kho, phải có **atomic conditional update** hoặc cơ chế tương đương tại điểm quyết định, không dùng một con số tồn kho trong search index để quyết định.

Đây không có nghĩa mọi cơ sở dữ liệu NoSQL đều mặc định linearizable. Tính đúng phụ thuộc sản phẩm, phạm vi nguyên tử (một item/document hay nhiều item), cấu hình consistency, transaction và cách ứng dụng kiểm tra trạng thái cũ.

### 3.2. Eventual consistency giữa các bản dẫn xuất

Với bản sao cập nhật bất đồng bộ:

~~~text
10:00:00.000  Product Store commit version 18
10:00:00.050  Outbox event được chuyển tới message broker
10:00:00.300  Search projector nhận event
10:00:00.700  Index chứa version 18
10:00:00.900  Truy vấn search bắt đầu nhìn thấy version 18
~~~

Trong một khoảng thời gian sau commit, Product Store và Search Index có thể khác nhau. Nếu pipeline khỏe, bản sao dần **hội tụ** về trạng thái mới.

Nhưng **eventual consistency không tự đưa ra giới hạn thời gian**. Một consumer bị dừng 3 giờ vẫn có thể “eventually” cập nhật sau khi khởi động lại, trong khi trải nghiệm sản phẩm đã không đạt yêu cầu.

### 3.3. Bounded staleness và ngân sách độ lệch

**Giới hạn thời gian lệch (staleness bound/freshness budget)** là thời gian tối đa hoặc mục tiêu thời gian cho phép giữa trạng thái nguồn và trạng thái một bản sao được dùng để đọc.

Ví dụ hợp đồng:

> Sau khi một thay đổi sản phẩm được commit tại nguồn, ít nhất 99,9% thay đổi hợp lệ phải hiển thị trên đường tìm kiếm trong vòng 5 giây, đo ở thời điểm truy vấn search trả phiên bản mới. Nếu pipeline vượt ngưỡng, phải cảnh báo và hiển thị/truy cập đường dự phòng phù hợp.

Đó là một **freshness SLO thống kê**, **không phải bảo đảm cứng rằng không bản ghi nào cũ quá 5 giây**. Muốn một đường đọc tuyệt đối không phục vụ dữ liệu cũ quá ngưỡng, hệ thống phải có cách **kiểm chứng freshness tại thời điểm đọc** và hành vi xác định khi không thể đáp ứng (chờ, đọc nguồn, hạn chế chức năng hoặc trả lỗi).

| Hợp đồng | Ý nghĩa | Ví dụ sử dụng |
| --- | --- | --- |
| **Strong/linearizable tại điểm quyết định** | Các thao tác tuân theo thứ tự và phạm vi nguyên tử được định nghĩa | Giữ hàng, cấp quyền, thanh toán |
| **Read-your-writes** | Người vừa ghi nhìn thấy thay đổi của chính mình | Người bán sửa giá rồi xem trang quản trị |
| **Monotonic reads** | Phiên đọc không bị quay về phiên bản cũ hơn đã nhìn thấy | Người dùng chuyển qua nhiều replica/search node |
| **Eventual consistency** | Bản sao tiến tới hội tụ nếu đồng bộ tiếp tục đúng | Search và báo cáo |
| **Freshness SLO theo phần trăm** | Một tỷ lệ thay đổi đạt độ trễ hiển thị mục tiêu | 99,9% index dưới 5 giây |
| **Hard freshness bound khi đọc** | Không phục vụ bản quá cũ; phải có kiểm tra/fallback | Thông tin rủi ro hoặc giá trị cần giới hạn nghiêm ngặt |
| **Snapshot cố định** | Giá trị phản ánh một thời điểm lịch sử đã chốt | Order line, hóa đơn |

**Không dùng một nhãn “consistent” chung cho tất cả đường đọc.** Một trang có thể dùng dữ liệu search trễ 5 giây để hiển thị, nhưng nút “Đặt hàng” phải kiểm tra lại giá/tồn kho bằng cơ chế đúng đắn riêng.

## 4. Xây dựng “ngân sách độ lệch” theo từng trường và thao tác

Một bản sao có thể chứa nhiều trường với mức nhạy cảm khác nhau. Không nên áp dụng một TTL hoặc một SLO cho tất cả.

| Dữ liệu/đường sử dụng | Mức trễ minh họa | Hành vi nếu vượt ngưỡng | Lý do |
| --- | --- | --- | --- |
| Tên/mô tả sản phẩm ở search | 30 giây tại p99 | Cảnh báo, đọc chi tiết từ nguồn nếu cần | Thường ít gây hậu quả trực tiếp |
| Giá hiển thị trên danh sách | 5 giây tại p99 | Hiển thị “giá có thể thay đổi”, xác minh khi checkout | Trải nghiệm cần gần mới, nhưng không được chốt từ cache |
| Số lượng “còn hàng” trên listing | 5 giây tại p99 | Hiển thị ước lượng, quyết định giữ hàng tại Inventory | Tránh oversell |
| Giá được chốt trong đơn | Theo thao tác xác nhận | Thất bại/đọc lại nếu trạng thái không đáp ứng | Trách nhiệm tài chính |
| Thu hồi quyền truy cập | Theo chính sách bảo mật, có thể cần hiệu lực ngay | Từ chối hoặc tra nguồn có thẩm quyền | Dữ liệu cũ có thể cho phép truy cập sai |
| Báo cáo doanh thu theo giờ | 5 phút | Gắn mốc “cập nhật đến ...”, chạy bù trừ | Không phải đường giao dịch tức thời |
| Order snapshot đã chốt | Không tự đồng bộ theo Catalog | Không thay giá lịch sử khi Catalog đổi | Giữ sự thật của giao dịch cũ |

Các mốc **5 giây/30 giây/5 phút là ví dụ**, không phải ngưỡng phổ quát. Yêu cầu thực cần được quyết định từ tác động nghiệp vụ, SLO người dùng, điều kiện hạ tầng và khả năng đo lường.

### 4.1. Lệch về thời gian khác lệch về giá trị

Giả sử giá nguồn đổi từ 1.500.000 xuống 1.390.000 VND, search trễ 2 giây. Có **hai đại lượng khác nhau**:

- **Độ trễ thời gian:** bản search nhận thay đổi sau 2 giây.
- **Sai khác giá trị:** 110.000 VND trong khoảng 2 giây đó.

Một bản sao có độ trễ “chỉ 2 giây” có thể vẫn gây thiệt hại lớn nếu đó là thay đổi tồn kho hoặc quyền truy cập. Ngược lại, một báo cáo tổng hợp 5 phút cũ có thể chấp nhận được nếu người dùng biết rõ thời điểm dữ liệu được cập nhật.

Độ lệch thời gian cần được đặt cạnh **mức quan trọng của sự thật** chứ không đánh giá độc lập.

### 4.2. Mục tiêu trung bình không bảo vệ đuôi trễ

Giả sử 999 thay đổi cập nhật search trong 200 ms, một thay đổi mất 10 phút. Thời gian trung bình trông rất nhỏ, nhưng **một sản phẩm có thể hiển thị giá cũ 10 phút**.

Nên theo dõi:

- p50, p95, **p99/p99.9** của độ trễ hiển thị.
- **Tuổi của thay đổi cũ nhất chưa được áp dụng**, không chỉ độ trễ trung bình.
- Tỷ lệ thay đổi vượt 5 giây, 30 giây, 1 phút.
- Số bản sao có version thấp hơn nguồn ở các tập bản ghi kiểm tra.
- Tỷ lệ **thiếu event, xử lý lỗi, retry, dead-letter** và backlog.

Không tính latency chỉ trên những thay đổi đã hoàn thành rồi bỏ qua sự kiện **kẹt mãi chưa áp dụng**: như vậy số đo sẽ lạc quan giả.

## 5. Định nghĩa chính xác độ trễ cần đo

Ký hiệu:

- **t_commit:** thời điểm thay đổi được commit ở nguồn có thẩm quyền.
- **t_publish:** thời điểm thông điệp thay đổi được xuất khỏi cơ chế ghi nguồn.
- **t_consume:** thời điểm projector nhận thông điệp.
- **t_apply:** thời điểm bản dẫn xuất đã lưu trạng thái mới.
- **t_visible:** thời điểm **đường truy vấn thực tế** có thể trả phiên bản mới.

Khi có các mốc đo đáng tin:

\[
L_{\text{end-to-end}}=t_{\text{visible}}-t_{\text{commit}}
\]

Có thể tách:

\[
L_{\text{end-to-end}} =
(t_{\text{publish}}-t_{\text{commit}})
+(t_{\text{consume}}-t_{\text{publish}})
+(t_{\text{apply}}-t_{\text{consume}})
+(t_{\text{visible}}-t_{\text{apply}})
\]

Đây là mô hình phân rã để quan sát. Nó đặc biệt hữu ích với search index vì **projector báo “đã ghi thành công” chưa chắc search query nhìn thấy ngay**, tùy refresh/indexing semantics. Với cache, thời điểm một bản cũ bị vô hiệu hóa và thời điểm request mới nhìn thấy giá trị mới cũng có thể khác nhau.

### 5.1. Không đo nhầm event time với commit time

Một sự kiện có thể được tạo trên thiết bị lúc 09:00 nhưng gửi lên server lúc 09:30. Nếu dùng **eventTime** của thiết bị để đo “lag đồng bộ source → search”, kết quả 30 phút có thể phản ánh **đến muộn từ client**, không phải search projector chậm.

Nên phân biệt:

| Timestamp | Được tạo ở đâu | Dùng cho mục đích nào? |
| --- | --- | --- |
| eventTime | Nguồn nghiệp vụ/thiết bị | Sắp xếp theo thời gian sự kiện |
| serverAcceptedAt | Server tiếp nhận và chấp nhận request | Truy vết thời điểm tiếp nhận |
| committedAt | Nguồn có thẩm quyền hoặc transaction metadata | Bắt đầu đo độ trễ sau commit |
| publishedAt | Outbox/CDC/broker | Đo chậm ở khâu xuất sự kiện |
| appliedAt | Consumer/projection | Đo tiến độ xử lý |
| visibleAt | Kiểm tra ở chính đường truy vấn đọc | Đo trải nghiệm thực tế |

Nếu timestamp được ghi trên **nhiều máy có đồng hồ lệch**, hiệu giữa hai đồng hồ có thể không đủ chính xác để chứng minh mục tiêu vài chục mili giây. Cần đồng bộ đồng hồ, theo dõi sai lệch, dùng mốc từ cùng nguồn đo khi có thể, hoặc đo dựa trên **sequence/version và probe** thay vì tin tuyệt đối vào timestamp từ mọi node.

### 5.2. Lag theo thời gian và lag theo số bản ghi

Hai chỉ số phổ biến:

~~~text
Source version product P-42 = 18
Search version product P-42 = 16
=> Search chậm 2 version cho sản phẩm này.

Source stream checkpoint = 12.000
Consumer checkpoint = 11.800
=> Consumer chưa đi qua 200 thay đổi của stream đó.
~~~

**Version lag** hoặc **checkpoint lag** giúp nhận biết dữ liệu còn thiếu, nhưng **không tự chuyển được thành “chậm 3 giây”**: 200 event có thể phát sinh trong 20 ms hoặc 20 phút. Ngược lại, một stream không có event mới có thể có checkpoint “đã bắt kịp” nhưng đường truy vấn vẫn chưa được kiểm tra về tính hiển thị.

Khi cần đo freshness thực, kết hợp **tuổi sự kiện chưa áp dụng, offset/checkpoint, synthetic probes và đối soát phiên bản**.

## 6. Vì sao ghi kép trực tiếp (dual write) dễ mất nhất quán?

Một cách làm có vẻ đơn giản:

~~~text
API updateProduct():
  1. Update Product Store
  2. Update Search Index
  3. Delete cache
  4. Trả success
~~~

Nhưng ứng dụng có thể chết sau bước 1, trước bước 2. Product Store đã commit mà search không được cập nhật.

~~~text
T0  Product Store: P-42 price=1.390.000, version=18 (COMMITTED)
T1  API process crash
T2  Search Index: P-42 price=1.500.000, version=17
T3  Không có bản ghi đáng tin nào để biết cần đồng bộ lại
~~~

Đổi thứ tự ghi search trước nguồn cũng không giải quyết: search có thể hiển thị giá chưa từng được nguồn commit. Retry mù có thể ghi sự kiện trùng hoặc tạo thứ tự cập nhật sai.

### 6.1. Transactional outbox

Một cách phổ biến là **ghi thay đổi nguồn và một bản ghi outbox trong cùng một giao dịch nguyên tử** tại kho có thẩm quyền, khi công nghệ và ranh giới lưu trữ hỗ trợ.

~~~mermaid
sequenceDiagram
    participant API as Product API
    participant DB as Product DB
    participant Relay as Outbox relay
    participant Bus as Event bus
    participant Projection as Search projector
    participant Search as Search index
    API->>DB: Begin transaction
    API->>DB: Update product version=18
    API->>DB: Insert outbox event ProductUpdated v18
    API->>DB: Commit both
    DB-->>API: Commit success
    Relay->>DB: Read pending outbox
    Relay->>Bus: Publish event
    Bus->>Projection: Deliver event (may repeat)
    Projection->>Search: Apply only permitted version
    Projection-->>Bus: Ack after durable apply
~~~

Điểm mạnh là **không mất thông tin cần đồng bộ chỉ vì tiến trình API chết ngay sau khi commit**. Relay có thể khởi động lại và tiếp tục đọc outbox.

Tuy nhiên, vẫn có khoảng trống:

- Relay có thể publish thành công nhưng chết **trước khi đánh dấu outbox đã gửi** → event được publish lại.
- Consumer có thể ghi thành công vào index nhưng chết **trước khi ACK** → event được giao lại.
- Search index có thể lỗi tạm hoặc chậm refresh.

Do đó outbox thường đi cùng **at-least-once delivery, xử lý idempotent, retry, giám sát lag và đối soát**. Outbox **không tự tạo một transaction ACID giữa Product DB, broker và search index**.

### 6.2. Change Data Capture (CDC)

Một lựa chọn khác là **CDC**: đọc log thay đổi của kho nguồn rồi chuyển thành sự kiện cho consumer.

Ưu điểm:

- Giảm rủi ro ứng dụng quên phát sự kiện sau commit.
- Ghi nhận các thay đổi ở đường ghi nguồn mà CDC thực sự quan sát.
- Có thể cung cấp điểm tiếp tục theo log offset/cursor.

Nhưng cần kiểm tra:

- Log có chứa đủ ngữ nghĩa nghiệp vụ hay chỉ biết các field đã thay đổi?
- Consumer có thể tái dựng trạng thái cuối chính xác không?
- Thay đổi schema, delete, transaction boundary và các event tới muộn được biểu diễn thế nào?
- Retention của change log có đủ khi consumer dừng dài ngày?
- CDC có bảo đảm thứ tự **theo một aggregate/key** hay không; nếu không, xử lý reorder ở consumer thế nào?

**Outbox và CDC có thể kết hợp**: outbox ghi sự kiện miền trong transaction, CDC chuyển chính những bản ghi outbox. Đó là một kiến trúc phổ biến nhưng vẫn đòi cơ chế xử lý trùng và phục hồi.

## 7. Phiên bản dữ liệu là nền tảng hội tụ

Nếu chỉ đưa giá trị mới mà không có **version**, hai event đến sai thứ tự có thể ghi đè trạng thái đúng bằng trạng thái cũ.

Ví dụ:

~~~text
Product P-42:
  version 16: price = 1.590.000
  version 17: price = 1.500.000
  version 18: price = 1.390.000

Consumer nhận:
  ProductUpdated(version=18)
  ProductUpdated(version=17)   ← đến muộn
~~~

Nếu consumer cứ ghi theo **thứ tự nhận**, search kết thúc ở giá **1.500.000**, dù nguồn đã ở version 18.

### 7.1. Mẫu event có danh tính và version

~~~json
{
  "eventId": "evt-8f9d",
  "eventType": "ProductUpdated",
  "schemaVersion": 2,
  "aggregateType": "Product",
  "aggregateId": "P-42",
  "aggregateVersion": 18,
  "committedAt": "2026-11-14T10:00:00Z",
  "payload": {
    "productId": "P-42",
    "name": "Bàn làm việc",
    "priceMinor": 1390000,
    "currency": "VND",
    "active": true
  }
}
~~~

Các trường đóng vai trò khác nhau:

- **eventId:** định danh thông điệp để phát hiện xử lý lặp.
- **aggregateId:** xác định thực thể nghiệp vụ cần cập nhật.
- **aggregateVersion:** số phiên bản tăng **trong phạm vi thực thể đó**, có nguồn phát hành đáng tin.
- **schemaVersion:** phiên bản hợp đồng payload, không phải phiên bản trạng thái của sản phẩm.
- **committedAt:** phục vụ quan sát thời gian đồng bộ nếu mốc tin cậy.
- **payload:** trạng thái hoặc phần thay đổi cần áp dụng, với ngữ nghĩa được định nghĩa rõ.

**Không dùng timestamp của thiết bị hoặc thời gian đến consumer để quyết định phiên bản nào mới hơn** nếu nguồn đã có sequence/version đủ tin cậy.

### 7.2. Với event chứa toàn bộ trạng thái

Nếu event là **full-state snapshot** (các field cần thiết cho read model đều có trong payload), consumer có thể có quy tắc:

~~~text
applyFullState(event):
    current = projection.get(event.aggregateId)

    if current exists and event.version <= current.version:
        return ALREADY_APPLIED_OR_STALE

    atomicUpsertIfNewer(
        key = event.aggregateId,
        newVersion = event.version,
        newState = event.payload
    )
~~~

Điều kiện **atomicUpsertIfNewer** phải được thực thi với một cơ chế có tính nguyên tử hoặc xử lý xung đột phù hợp. Không chỉ đọc version rồi ghi vô điều kiện: hai consumer có thể đọc cùng version cũ và ghi ngược thứ tự.

Đối với full-state event, đôi khi có thể bỏ qua version trung gian 17 và áp dụng trực tiếp 18, vì 18 chứa toàn bộ các trường cần thiết. Tuy vậy, nếu read model có tác dụng phụ như gửi email, cập nhật thống kê đếm theo event, hoặc mỗi event chứa luật nghiệp vụ riêng, **bỏ qua bản trung gian có thể sai**.

### 7.3. Với event dạng thay đổi tương đối (delta)

Giả sử event chỉ nói:

~~~json
{
  "aggregateId": "inventory:SKU-8",
  "aggregateVersion": 18,
  "quantityDelta": -1
}
~~~

Nếu consumer đang ở version 16 và nhận version 18, **không thể tự áp dụng -1 rồi nhảy version lên 18** nếu version 17 là một thay đổi -2 chưa đến. Làm vậy sẽ mất cập nhật và phá invariant.

Với delta event cần:

1. Biết expected next version/sequence trong phạm vi aggregate.
2. Chỉ áp dụng version **liền sau** khi ngữ nghĩa đòi hỏi đủ từng bước.
3. Lưu event đến trước để chờ, hoặc yêu cầu replay/tải lại snapshot nguồn khi phát hiện khoảng trống.
4. Dedup event đã áp dụng; chỉ ACK khi trạng thái và checkpoint cần thiết được lưu bền vững.

**Version cao hơn chưa chắc có thể áp dụng ngay**; điều đó phụ thuộc payload là **trạng thái đầy đủ** hay **delta cần tất cả bước trước**.

### 7.4. Version theo aggregate không phải thứ tự toàn cục

Version 18 của P-42 không nói thay đổi nào xảy ra trước version 7 của P-91. Nếu một báo cáo cần trật tự toàn hệ thống, phải dùng log offset/sequence hoặc giao thức phù hợp với nguồn sự kiện và yêu cầu, không so sánh hai aggregateVersion không liên quan.

Trong hệ nhiều nguồn có thể cùng cập nhật một thực thể, **một counter đơn ở mỗi service** cũng không tự giải quyết xung đột. Nên phân định một nguồn có thẩm quyền hoặc thiết kế merge/coordination đặc biệt với ngữ nghĩa rõ ràng.

## 8. Xóa dữ liệu và tránh “hồi sinh” bản ghi cũ

Xóa là tình huống dễ làm lộ lỗi đồng bộ.

~~~text
10:00  ProductUpdated version 17
10:01  ProductDeleted version 18
10:02  Search áp dụng Delete v18, sản phẩm biến mất
10:03  Event ProductUpdated v17 được retry và đến muộn
~~~

Nếu consumer thấy index không còn document rồi **insert lại từ v17**, sản phẩm bị **hồi sinh** dù nguồn đã xóa.

Một phương án là giữ **tombstone hoặc metadata phiên bản đã xóa**:

~~~text
Projection state:
    productId: P-42
    version: 18
    deleted: true

Khi event v17 đến:
    v17 <= stored v18 → bỏ qua
~~~

Trong một số search engine hoặc cache, delete vật lý có thể làm mất chính dữ liệu version dùng để so sánh. Khi đó cần kế hoạch **bảo vệ tombstone/sequence**, chẳng hạn lưu metadata riêng, dùng external versioning theo khả năng engine hoặc xử lý qua projection store có thẩm quyền.

**TTL của tombstone là quyết định nguy hiểm nếu không xét thời gian replay**: hết tombstone quá sớm trong khi event cũ vẫn còn có thể được phát lại sẽ mở đường cho việc hồi sinh.

### 8.1. Xóa tài khoản và dữ liệu cá nhân

Một yêu cầu xóa người dùng có thể phải lan tới:

- Profile source.
- Search index và cache.
- Read model của các dịch vụ khác.
- Hệ thống analytics/log nếu có dữ liệu cá nhân.
- Snapshot, archive và backup theo chính sách phù hợp.

Độ trễ đồng bộ **không được dùng để biện minh cho việc tiếp tục cấp quyền truy cập** khi quyền đã bị thu hồi theo chính sách yêu cầu hiệu lực ngay. Đường quyết định bảo mật có thể phải kiểm tra nguồn có thẩm quyền hoặc một cơ chế token/permission có hợp đồng thu hồi rõ ràng.

Việc “search không còn kết quả” **không chứng minh dữ liệu đã được xóa khỏi mọi bản sao**. Cần quy trình retention, deletion tracking và đối soát theo yêu cầu pháp lý/nghiệp vụ thực tế.

## 9. Cache và race: bản sao có thể cũ lại sau khi đã mới

Ngay cả khi có invalidation khi ghi, **cache-aside** vẫn có một tình huống cạnh tranh:

~~~text
T1  Reader A: cache miss; bắt đầu đọc Product Store version 17
T2  Writer B: commit Product Store version 18
T3  Writer B: xóa cache P-42
T4  Reader A: trả về version 17 vừa đọc xong
T5  Reader A: ghi version 17 vào cache với TTL 5 phút
T6  Reader C: đọc cache version 17
~~~

Tại T3 cache đã được vô hiệu hóa, nhưng T5 **đưa lại giá trị cũ**. Đây là race giữa **cache fill và invalidation**; chỉ đặt TTL ngắn không khắc phục tận gốc.

Những kỹ thuật có thể cân nhắc:

- **Versioned cache entry:** lưu version cùng giá trị, chỉ cho phép cập nhật theo phiên bản cao hơn nếu hạ tầng hỗ trợ phép ghi có điều kiện đáng tin.
- **Kiểm tra version khi fill:** so với mốc thế hệ/invalidation; phải thực hiện nguyên tử để không mở một race khác.
- **Versioned key:** ví dụ product:P-42:v18; cần một nguồn đáng tin để biết version hiện hành và quản lý khóa cũ.
- **Invalidate sau commit** bằng sự kiện bền vững, có retry và giám sát; vẫn phải xét các reader đang lấy dữ liệu cũ.
- **Read from source** cho thao tác cần mới nhất, không coi cache là nguồn quyết định.

Phải phân biệt **bản cache hợp lệ theo TTL** với **bản cache hợp lệ theo phiên bản nghiệp vụ**. TTL 5 phút chỉ giới hạn vòng đời cache theo thời gian đã đặt; nó không chứng minh giá trị đó còn là trạng thái mới nhất.

## 10. Read-your-writes khi bản sao chưa kịp cập nhật

Một trải nghiệm khó chịu:

~~~text
10:00:00  Người bán bấm "Lưu giá mới": API báo thành công
10:00:01  Trang quản trị tìm lại sản phẩm qua search → giá cũ
10:00:03  Search đồng bộ xong → giá mới
~~~

Về mặt kỹ thuật, search có thể nằm trong SLO 5 giây, nhưng người vừa sửa thường mong nhìn thấy ngay thay đổi **của chính họ**.

### 10.1. Trả lại version đã commit

API ghi có thể trả:

~~~json
{
  "productId": "P-42",
  "committedVersion": 18,
  "committedPriceMinor": 1390000
}
~~~

Client giữ **committedVersion=18** trong ngữ cảnh tương tác. Khi thực hiện đọc tiếp, có các chiến lược:

1. **Đọc thẳng nguồn** cho thao tác vừa cập nhật.
2. **Chờ projection đạt version >= 18** với timeout ngắn; nếu timeout thì đọc nguồn hoặc báo trạng thái đang đồng bộ.
3. **Cập nhật giao diện từ phản hồi ghi** cho trải nghiệm tức thời, nhưng không nhầm hiển thị lạc quan với dữ liệu đã commit khi API chưa xác nhận.
4. **Định tuyến sticky/session** tới đường đọc có thể bảo đảm version, nếu hạ tầng thực sự hỗ trợ.

Ví dụ giả mã:

~~~text
getProductForEditor(productId, requiredVersion):
    p = searchReadModel.get(productId)
    if p != null and p.version >= requiredVersion:
        return p

    authoritative = productStore.get(productId)
    return authoritative
~~~

Tùy thao tác, bản nguồn có thể cần một mức đọc nhất quán phù hợp; nếu chính Product Store có nhiều replica với độ trễ, đọc từ một replica chậm không tự bảo đảm read-your-writes.

### 10.2. Monotonic reads

Một phiên có thể lần lượt đọc version 18 rồi version 17 nếu request bị định tuyến qua các bản sao có độ mới khác nhau.

~~~text
Lần 1: Search node A trả version 18
Lần 2: Search node B trả version 17
~~~

Nếu ứng dụng yêu cầu **không quay lùi**, có thể mang theo phiên bản cao nhất mà phiên đã nhìn thấy và chỉ chấp nhận dữ liệu đáp ứng version đó; khi chưa đáp ứng thì chờ hoặc fallback. Cần lưu ý **version theo từng thực thể**, không dùng một version của P-42 để so với P-91.

Những cơ chế này cải thiện trải nghiệm nhưng có chi phí độ trễ và lưu lượng đọc nguồn. Chỉ áp dụng cho những đường cần hợp đồng đó.

## 11. Cập nhật nhiều bản sao trong một transaction có giải quyết tất cả không?

Nếu nhiều bản sao nằm **trong cùng ranh giới giao dịch của một database** và sản phẩm hỗ trợ transaction phù hợp, cập nhật đồng bộ có thể đem lại trạng thái nhất quán sau commit theo hợp đồng của database.

Nhưng khi dữ liệu đi qua **MongoDB → message broker → OpenSearch → Redis → analytics**, không có một transaction database thông thường nào tự bao trùm tất cả hệ thống. Buộc API chờ mọi nơi cập nhật trong một chuỗi RPC cũng không tạo ra atomicity xuyên các thành phần:

~~~text
Update source: SUCCESS
Update search: SUCCESS
Invalidate cache: TIMEOUT (không biết đã xóa hay chưa)
=> API nên báo thành công hay thất bại?
~~~

Nếu đã commit nguồn, trả “toàn bộ thao tác thất bại” rồi client retry có thể gây hiệu ứng trùng. Nếu báo thành công, phải chấp nhận rằng bản dẫn xuất có thể đang chậm.

Mẫu phổ biến là:

- **Nguồn có thẩm quyền commit một cách đúng đắn.**
- **Sự kiện thay đổi được lưu bền vững cùng quyết định nguồn.**
- **Các bản đọc dẫn xuất đồng bộ bất đồng bộ và idempotent.**
- **Đường đọc quan trọng kiểm tra/fallback nếu bản dẫn xuất chưa đủ mới.**
- **Hệ thống đo lag, cảnh báo và có cách tái dựng bản sao.**

Không phải hệ nào cũng cần tất cả thành phần này; quyết định theo số lượng bản sao, tác động nghiệp vụ và chi phí vận hành.

## 12. Khi trễ hơn ngân sách: hợp đồng suy giảm có kiểm soát

Một freshness SLO có giá trị khi hệ thống biết **sẽ làm gì nếu vi phạm**.

| Đường sử dụng | Bản sao vượt lag budget | Hành vi phù hợp có thể cân nhắc |
| --- | --- | --- |
| Kết quả tìm kiếm | Search chậm 2 phút | Hiển thị cảnh báo độ mới, hạn chế một số lọc/giá, chuyển tới chi tiết nguồn nếu cần |
| Trang quản trị vừa sửa | Search chưa đạt version yêu cầu | Đọc nguồn hoặc chờ có timeout |
| Trang sản phẩm | Cache chậm hoặc lỗi | Cache miss → đọc nguồn, có rate limit/single-flight để bảo vệ nguồn |
| Checkout | Giá/tồn kho có thể cũ | **Bắt buộc xác minh/ghi điều kiện ở nguồn có thẩm quyền** |
| Báo cáo | Rollup chậm 10 phút | Hiển thị mốc dữ liệu cuối, giữ trạng thái “đang cập nhật”, cho phép chạy lại |
| Phân quyền | Bản sao quyền bị chậm | Theo chính sách, từ chối tạm hoặc kiểm tra nguồn an toàn; không mặc nhiên cho phép |

**Không phải fallback nào cũng luôn an toàn.** Nếu tất cả request đồng loạt bỏ cache để về nguồn, nguồn có thể sập. Cần đặt **timeout, circuit breaker, request coalescing, rate limiting, backpressure và capacity headroom** theo đường thực tế.

### 12.1. Dùng “stale-while-revalidate” ở đâu?

Stale-while-revalidate phục vụ bản dữ liệu cũ trong lúc nền làm mới. Nó có thể hợp lý cho:

- Danh sách bài viết hoặc đề xuất sản phẩm.
- Một số metadata ít nhạy cảm.
- Dashboard không cần thời gian thực tuyệt đối, có hiển thị tuổi dữ liệu.

Nhưng không phù hợp làm nguồn quyết định khi có bất biến mạnh như:

- Chốt giá thanh toán.
- Cấp phát tồn kho.
- Xác thực quyền vừa bị thu hồi.
- Ngăn một người đặt hai lần vào cùng slot.

Nếu cache đã xóa/expire giá trị vật lý, muốn phục vụ stale cần có cơ chế **giữ bản cũ riêng** cùng giới hạn thời gian, không giả định có thể đọc lại một key đã bị dọn.

## 13. Consumer lag, backlog và khả năng bắt kịp

Giả sử nguồn phát **1.000 sự kiện/giây**, consumer chỉ xử lý **700 sự kiện/giây** trong 10 phút.

Backlog tăng gần đúng:

\[
(1000-700)\times600=180.000\text{ sự kiện}
\]

Sau đó nhóm tăng năng lực consumer lên **1.500 sự kiện/giây**, trong khi nguồn vẫn phát **1.000 sự kiện/giây**. Nếu điều kiện đều, không có retry/chi phí đặc biệt và consumer xử lý đúng thứ tự cần thiết, tốc độ rút backlog ròng là:

\[
1500-1000=500\text{ sự kiện/giây}
\]

Thời gian lý tưởng để rút backlog:

\[
\frac{180000}{500}=360\text{ giây} = 6\text{ phút}
\]

Trong 6 phút ấy, các event cũ có thể vẫn chưa được nhìn thấy trên bản sao. Một consumer “đã chạy lại” **không đồng nghĩa đã bắt kịp freshness SLO**.

### 13.1. Không chỉ đếm số message còn trong queue

Một queue có 5.000 message rất mới có thể chỉ chậm vài giây, còn queue có 100 message bị kẹt nhiều giờ lại vi phạm nặng. Nên theo dõi:

- **Oldest unprocessed event age.**
- Consumer progress/checkpoint theo partition của stream.
- Số event được source commit nhưng chưa tới search/read model.
- Tốc độ ingest, throughput xử lý và tốc độ rút backlog ròng.
- Tỷ lệ lỗi ứng với từng event/aggregate, retry và DLQ.
- Thời gian **search query nhìn thấy** version đã áp dụng.
- Sự kiện mất/bị bỏ qua khi log retention hết trước khi consumer bắt kịp.

Nếu sự kiện mới không phát sinh trong thời gian dài, một metric đo “lag từ event cuối đã xử lý” có thể không chứng minh pipeline còn sống. Có thể dùng **heartbeat/probe** hoặc theo dõi checkpoint và tình trạng consumer để tránh kết luận “lag = 0” khi pipeline thực ra ngừng hoạt động.

## 14. Đối soát định kỳ: tại sao vẫn cần khi đã có outbox?

Outbox giúp giảm nguy cơ mất thông điệp sau commit, nhưng vận hành thực tế vẫn có thể gặp:

- Event bị lưu vào dead-letter queue nhưng chưa được replay.
- Schema mới không tương thích với consumer cũ.
- Bug trong phép ánh xạ trường làm sai bản dẫn xuất.
- Một lần reindex tạo dữ liệu thiếu trường.
- Event delete chưa được áp dụng hoặc tombstone bị mất.
- Sự cố phục hồi dữ liệu đưa một bản sao về snapshot cũ.
- Consumer “ACK nhầm” trước khi trạng thái thực sự được lưu bền vững.

Vì thế, cần cơ chế **reconciliation** so sánh nguồn và các bản sao theo **version, checksum hoặc bất biến nghiệp vụ**.

### 14.1. Mẫu kiểm tra phiên bản

~~~text
Product Store:
  P-42 version=18 price=1390000
  P-43 version=11 price=800000
  P-44 version=9  deleted=true

Search:
  P-42 version=18 price=1390000    → OK
  P-43 version=10 price=750000     → STALE
  P-44 version=8  active=true      → WRONG / missed delete
~~~

Một job có thể liệt kê các ID/version theo shard hoặc theo khoảng thay đổi, sau đó so sánh và đưa những bản sai về trạng thái mới nhất. Cần kiểm soát:

- **Nguồn được đọc ở một snapshot/checkpoint nào** để không báo false mismatch vì nguồn thay đổi giữa lúc scan?
- Đối soát theo mẫu hay toàn bộ? Tần suất và chi phí?
- Consumer đồng thời đang cập nhật có thể gây xung đột với job repair không?
- Repair có dùng **upsert-if-newer** để tránh ghi đè bản mới bằng snapshot cũ không?
- Có ghi lại **số bản ghi lệch và tuổi lệch** để kiểm chứng hiệu quả không?

Đối soát là **lưới an toàn**, không thay thế thiết kế đồng bộ đáng tin và kiểm tra invariant tại nguồn.

### 14.2. Rebuild projection từ đầu

Khi cần xây lại search index/read model:

1. Chọn mốc snapshot hoặc checkpoint của dữ liệu nguồn.
2. Đọc dữ liệu nguồn theo trang/batch, không khóa hệ thống lâu nếu có thể tránh.
3. Đồng thời giữ/đọc thay đổi phát sinh sau checkpoint.
4. Ghi dữ liệu vào **index/version mới**, áp dụng event sau snapshot theo version để không mất cập nhật.
5. Đối chiếu số lượng, phiên bản, các trường quan trọng và sample queries.
6. Chỉ chuyển đường đọc sang bản mới khi đạt điều kiện chấp nhận.
7. Giữ phương án rollback/khôi phục index cũ trong khoảng phù hợp.

Nếu chỉ “dump source rồi rebuild” trong khi source vẫn nhận ghi, có thể mất thay đổi xảy ra trong lúc chạy. Cần một **quy trình snapshot + catch-up** phù hợp với semantics và khả năng lưu log của công nghệ.

## 15. Thay đổi quan hệ và dữ liệu lặp còn có bài toán xóa/chuyển nhóm

Giả sử sản phẩm P-42 chuyển danh mục từ **FURNITURE** sang **OFFICE**. Search index có thể có hai kiểu dữ liệu dẫn xuất:

~~~text
products_by_category["FURNITURE"] chứa P-42
products_by_category["OFFICE"]    chưa chứa P-42
~~~

Consumer không chỉ “thêm P-42 vào OFFICE”; nó còn cần **bỏ P-42 khỏi FURNITURE**. Nếu chỉ nhận payload trạng thái mới mà không biết vị trí cũ, cần có cách truy vấn/truy vết membership hiện tại hoặc rebuild projection đúng.

Đây là ví dụ **quan hệ lặp trong dữ liệu phi chuẩn hóa**:

- Một thay đổi ở nguồn có thể ảnh hưởng **nhiều bản ghi dẫn xuất**.
- Nếu áp dụng hai bước không nguyên tử, có thể có khoảng thời gian P-42 xuất hiện ở cả hai nhóm hoặc không nhóm nào.
- Với UI thông thường có thể chấp nhận trễ ngắn; với hành động cần bất biến mạnh phải có điểm quyết định khác.
- Idempotency và version giúp hội tụ, nhưng **không tự bảo đảm mọi bản ghi dẫn xuất thay đổi đồng thời**.

Một lựa chọn là lưu projection theo **productId** rồi dùng chỉ mục trên category để đọc; một lựa chọn khác là nhiều tài liệu theo category. Mỗi cách có chi phí cập nhật, read path và mô hình nhất quán riêng.

### 15.1. Xung đột do nhiều nguồn ghi

Nếu Product Service cho sửa tên, còn Search Admin cũng cho sửa tên trực tiếp rồi đẩy ngược về Product, một tình huống:

~~~text
Product source: name = "Bàn A", version = 18
Search Admin:   name = "Bàn B", localVersion = 5
Product source: name = "Bàn C", version = 19
~~~

So sánh version 5 và 19 **không đủ**, vì hai version do hai nguồn khác nhau tạo. **Last-write-wins theo timestamp** cũng có thể làm mất thay đổi hợp lệ khi đồng hồ lệch hoặc thao tác tới trễ.

Các lựa chọn cần cân nhắc:

- Quy định **một chủ sở hữu viết** cho từng field.
- Chuyển lệnh sửa từ nơi khác thành **command tới nguồn có thẩm quyền**, không ghi ngược mù.
- Nếu thật sự cần multi-master, định nghĩa luật merge/conflict resolution theo từng trường và chấp nhận độ phức tạp (version vector, CRDT hoặc cơ chế phối hợp tùy bài toán).

Tính nhất quán giữa các bản sao sẽ dễ quản lý hơn nhiều khi **mỗi sự thật có chủ sở hữu rõ ràng**.

## 16. Schema evolution của sự kiện và bản dẫn xuất

Dữ liệu nguồn và consumer có thể triển khai ở các phiên bản khác nhau. Ví dụ ProductUpdated v1 chỉ có **name** và **priceMinor**, còn v2 bổ sung **taxCategory** và đổi cách mã hóa tiền.

Không nên phát hành source mới rồi giả định mọi consumer đã hiểu payload mới. Một quy trình:

1. Định nghĩa **schemaVersion** của event và quy tắc tương thích.
2. Triển khai consumer có thể đọc phiên bản cũ/mới trước khi thay đổi producer gây breaking change.
3. Đảm bảo field mới có default chỉ khi default **đúng ý nghĩa**, không gán bừa cho dữ liệu tiền tệ hoặc quyền.
4. Nếu cần đổi dữ liệu lưu, backfill/rebuild projection với checkpoint phù hợp.
5. Theo dõi event bị từ chối do schema, DLQ và tuổi message cũ.
6. Gỡ nhánh tương thích sau khi chắc chắn không còn replay cần dùng event cũ.

Đừng nhầm **event.schemaVersion** với **product.aggregateVersion**. Event v2 của Product v18 nói “hợp đồng payload phiên bản 2, trạng thái sản phẩm phiên bản 18”.

## 17. Bảo đảm đúng đắn khi một hành động cần nhiều bản sao

Một ứng dụng đặt phòng có thể lưu:

~~~text
Booking Store     : trạng thái xác nhận đặt phòng
Availability View : lịch phòng còn trống dùng tìm kiếm
Search Index      : các phòng phù hợp bộ lọc
Cache             : trang chi tiết phòng
~~~

Availability View có thể trễ vài giây. Nếu hai khách cùng xem phòng R-08 còn trống, cả hai có thể đều thấy “còn” mà **không tạo lỗi** ở bước xem. Lỗi chỉ xảy ra nếu hệ thống **cho phép cả hai xác nhận thành công cùng slot** dựa trên view đó.

Thiết kế phải có bước quyết định có thẩm quyền:

~~~text
Search → Hiển thị các phòng có khả năng còn trống
       → Người dùng chọn phòng/khung giờ
       → Booking Authority kiểm tra + giữ chỗ nguyên tử
       → Trả xác nhận hoặc hết chỗ
       → Phát BookingConfirmed/Cancelled
       → Cập nhật availability projection và search
~~~

**Bản sao được phép lệch** trong đường khám phá, nhưng **bất biến không đặt trùng** phải được bảo vệ ở điểm ghi nguyên tử. Điều này cho phép khả năng đọc lớn mà vẫn giữ tính đúng nghiệp vụ.

### 17.1. Không sửa bằng cách “đợi N giây rồi tin dữ liệu đã mới”

Một cách sai:

~~~text
Update booking nguồn
sleep(5 giây)
đọc search, coi là đã đồng bộ
~~~

Nếu consumer lỗi, queue backlog hay index chưa visible, chờ cố định 5 giây không bảo đảm gì. Phải dùng **version/checkpoint/readiness** hoặc kiểm tra tại nguồn khi thao tác yêu cầu. Khoảng chờ có thể dùng để giảm tần suất thử lại, **không phải bằng chứng về tính nhất quán**.

## 18. Observability và cảnh báo cho độ lệch

Cần quan sát từng chặng, từng nhóm entity và cả **kết quả đọc thực tế**, không chỉ quan sát broker.

| Nhóm metric | Cần theo dõi | Ví dụ hành động |
| --- | --- | --- |
| Outbox | Tuổi bản ghi chưa publish, số pending, lỗi relay | Khởi động/sửa relay, kiểm tra backlog |
| Broker/CDC | Lag theo offset, oldest unprocessed age, lỗi giữ log | Scale consumer hoặc xử lý lỗi input |
| Projector | p95/p99 thời gian apply, retries, DLQ, version gaps | Điều tra event/aggregate cụ thể |
| Search | Refresh/query visibility lag, document version mismatch | Kiểm tra index ingest/refresh, chạy repair |
| Cache | Hit/miss, stale version, invalidation failures, age | Kiểm tra race, TTL và cache fill |
| Reconciliation | Tỷ lệ lệch, tuổi lệch, số deleted record hồi sinh | Backfill/replay, cải tiến tombstone |
| API | Read-your-writes fallback rate, p99 latency, freshness warning | Cân bằng độ mới với tải nguồn |
| Data quality | Thiếu bản ghi, duplicate, sai thứ tự và violation nghiệp vụ | Ngăn tác dụng phụ ở điểm quyết định |

### 18.1. Freshness SLI và mục tiêu

Một ví dụ SLI theo từng update được commit:

~~~text
freshness_5s_success_ratio =
  số thay đổi hợp lệ visible trong <= 5 giây
  -------------------------------------------------
  tổng số thay đổi hợp lệ được commit trong tập đo
~~~

Khi đo trong cửa sổ vận hành, phải nêu rõ:

- Tập thay đổi nào nằm trong mẫu?
- Có tính **delete, sửa giá, thay đổi danh mục** hay chỉ update thường?
- Nếu một thay đổi chưa bao giờ visible, có bị tính là **thất bại** không?
- Nếu source bị rollback hoặc update kế tiếp đến ngay, xác định visible của version trung gian như thế nào?
- Đường truy vấn nào được probe (truy vấn theo ID, keyword, lọc danh mục)?
- Cửa sổ đánh giá 1 giờ, 7 ngày hay 30 ngày, và số lượng mẫu đủ ý nghĩa không?

Với event đến liên tục nhanh hơn chu kỳ search refresh, một version trung gian có thể **không bao giờ được truy vấn nhìn thấy** vì đã bị thay bằng version mới hơn. Nếu hợp đồng chỉ cần **trạng thái mới nhất hội tụ** chứ không bắt mọi version trung gian visible, SLI phải phản ánh đúng mục tiêu đó. Không đánh đồng “mọi event đều phải từng xuất hiện trên UI” với “read model phải bắt kịp trạng thái hiện hành”.

### 18.2. Cảnh báo nên gắn với nguy cơ nghiệp vụ

Ví dụ:

- **Cảnh báo độ mới search** nếu oldest pending update quá 30 giây hoặc tỷ lệ đạt trong 5 giây giảm.
- **Cảnh báo nghiêm trọng** nếu delete/revocation chưa áp dụng trong giới hạn bảo mật.
- **Cảnh báo khả năng hồi phục** khi consumer lag tăng đều và tốc độ xử lý thấp hơn tốc độ nguồn.
- **Cảnh báo data quality** khi reconciliation phát hiện phiên bản đi lùi hoặc thiếu bản ghi kéo dài.

Cảnh báo không chỉ nêu “consumer lag cao” mà nên có **tác động dự kiến, nhóm dữ liệu ảnh hưởng, đường đọc cần fallback và cách khôi phục**.

## 19. Phép thử thực tế cho các bản sao nghiệp vụ

Một môi trường kiểm chứng nên có nguồn, outbox hoặc CDC, broker, projector, cache/search và đường query như production ở mức đại diện.

### 19.1. Ma trận thử nghiệm

| Kịch bản | Cách tạo | Kỳ vọng phải kiểm chứng |
| --- | --- | --- |
| **Normal flow** | Sửa 10.000 sản phẩm với mức tải thực tế | p95/p99 lag, số bản sao đúng version |
| **Crash sau commit nguồn** | Dừng API trước publish ở đường dual-write; so với outbox | Không mất thông tin thay đổi khi có outbox phù hợp |
| **Publish trùng** | Giao cùng event hai/ba lần | Projection idempotent, không gửi tác dụng phụ trùng |
| **Sai thứ tự** | Giao v18 trước v17 | Bản cuối vẫn ở v18 |
| **Mất delta v17** | Giao v18 dạng delta khi projection ở v16 | Không áp dụng sai; chờ/replay/resync |
| **Chậm 10 phút** | Dừng consumer, tiếp tục ghi nguồn | Freshness vi phạm được đo và cảnh báo; đường quan trọng fallback |
| **Reindex** | Tạo index mới trong khi source vẫn ghi | Snapshot + catch-up không bỏ sót version |
| **Delete rồi replay cũ** | Xóa v18 rồi gửi lại update v17 | Không hồi sinh bản đã xóa |
| **Đổi danh mục** | P-42 từ A sang B | Kết quả cuối không còn ở A và có ở B |
| **Concurrent updates** | Hai writer cùng sửa giá từ version cũ | Nguồn có kết quả nhất quán; projection hội tụ |
| **Read-your-writes** | Ghi v18 rồi đọc ngay qua nhiều đường | Người ghi không nhìn thấy v17 nếu hợp đồng yêu cầu v18 |
| **Schema rollout** | Producer v2, consumer v1/v2, replay event cũ | Không mất dữ liệu hoặc lỗi im lặng |
| **Cache fill race** | Reader giữ v17 rồi writer invalidates v18 | Cache không giữ bản cũ trái chính sách |

Các test phải có **điểm quan sát tại source và tại đường query cuối**, không chỉ kiểm tra rằng consumer đã ACK.

### 19.2. Đặc tả một phép thử

~~~yaml
experiment: derived-copy-freshness
source: product-store
targets:
  - search-index
  - product-listing
  - cache
workload:
  updatesPerSecond: 500
  readsPerSecond: 3000
  hotProductSharePercent: 20
  duplicateEventPercent: 5
  outOfOrderEventPercent: 5
  consumerPauseSeconds: 60
sourceContract:
  versionPerProduct: monotonic
  outboxAtomicWithSource: required
exampleSlo:
  searchVisibleWithinSeconds: 5
  targetPercent: 99.9
mustRemainTrue:
  - "no older version overwrites a newer version"
  - "deleted products do not reappear after replay"
  - "checkout uses authoritative price and stock decision"
  - "unapplied changes are detectable and replayable"
measure:
  - "commit-to-visible lag p50/p95/p99/p99.9"
  - "oldest pending update age"
  - "source/projection version mismatch"
  - "error, retry, DLQ and recovery duration"
  - "API read-your-writes fallback and p99"
~~~

Đây là **mẫu đặc tả**, không phải cấu hình có thể chạy trực tiếp. Ngưỡng 5 giây/99,9% và tải 500 updates/s chỉ dùng để thiết kế phép đo. Cần bổ sung phiên bản engine, topology, số replica, cấu hình index refresh/cache, loại máy, phân phối khóa và thời gian đánh giá.

### 19.3. Kết quả minh họa

| Kịch bản | p99 commit → visible | Bản sai khác còn tồn tại | Kết luận |
| --- | ---: | --- | --- |
| Bình thường | 1,2 giây | 0 sau khi pipeline bắt kịp | Đạt mục tiêu mẫu |
| Consumer chậm tạm | 12 giây | Có, trong thời gian backlog | Vi phạm freshness SLO |
| Retry/reorder không kiểm tra version | 2 giây | Có bản cuối ở version cũ | Đúng thời gian nhưng **sai trạng thái** |
| Retry/reorder + conditional version | 2,3 giây | 0 sau catch-up | Chịu trùng/sai thứ tự tốt hơn |
| Delete không giữ tombstone | 1,5 giây | Có sản phẩm bị hồi sinh | Sai ngữ nghĩa dù trễ thấp |

Số liệu **hoàn toàn minh họa**. Bài học quan trọng là **“nhanh” không đồng nghĩa “đúng”**: hệ thống có thể cập nhật rất nhanh nhưng mất thứ tự, đếm trùng hoặc hồi sinh dữ liệu đã xóa. Cần đo cả **thời gian lệch và bất biến cuối cùng**.

## 20. Quy trình ra quyết định khi muốn lặp một trường dữ liệu

Trước khi sao chép một trường từ nguồn A sang bản đọc B, hãy trả lời:

1. **Tại sao cần lặp?** Query nào nhanh hơn hoặc giảm call nào?
2. **Có phải snapshot lịch sử không?** Nếu có, thời điểm chốt và quy tắc giữ bất biến là gì?
3. **Nếu là bản dẫn xuất sống, ai có thẩm quyền sửa giá trị?**
4. **Độ lệch thời gian được phép là bao nhiêu?** Đây là mục tiêu theo p99 hay giới hạn cứng trên mọi lần đọc?
5. **Nếu vượt budget, đường đọc sẽ làm gì?** Chờ, đọc nguồn, phục vụ stale có nhãn hay từ chối?
6. **Sự kiện thay đổi có được ghi đáng tin cùng source commit không?**
7. **Có version và idempotency để chống duplicate, reorder và replay không?**
8. **Với delta event, có phát hiện mất phiên bản trung gian không?**
9. **Với delete và thay đổi quan hệ, bản cũ có được xóa đúng không?**
10. **Có thể backfill/rebuild từ nguồn mà không bỏ sót thay đổi mới không?**
11. **Có SLI đo thời gian tới trạng thái query-visible và reconciliation không?**
12. **Có trách nhiệm sở hữu và runbook xử lý lag vượt ngưỡng không?**

Nếu không thể trả lời các câu trên, một bản sao mới có thể làm tối ưu đọc trước mắt nhưng để lại nợ nhất quán khó kiểm soát.

## 21. Bài tập: profile, booking và search trong ứng dụng đặt phòng

Giả sử hệ thống có các kho:

~~~text
Customer Profile:
    customerId, fullName, phone, currentAddress, version

Booking:
    bookingId, customerId, guestNameSnapshot,
    contactPhoneSnapshot, roomId, checkIn, checkOut,
    priceSnapshot, status

Room Availability:
    roomId, day, available, version

Search Index:
    roomId, city, priceEstimate, availabilityEstimate,
    projectionVersion
~~~

Các yêu cầu:

- Người dùng sửa tên hiển thị; trang hồ sơ phải phản ánh ngay.
- Tên/điện thoại đã dùng khi xác nhận một booking phải được lưu theo quy tắc snapshot của giao dịch.
- Search phòng có thể chậm **tối đa mục tiêu 5 giây ở p99**, nhưng không được xác nhận hai booking trùng một phòng/khung giờ.
- Thao tác hủy booking phải trả lại khả dụng theo logic nghiệp vụ và phát thay đổi cho search.
- Consumer có thể nhận event trùng, sai thứ tự hoặc dừng trong 2 phút.
- Yêu cầu xóa thông tin cá nhân phải được xử lý theo chính sách ở các hệ thống liên quan.

### Phần A — Phân loại bản sao

Trong các trường **fullName**, **guestNameSnapshot**, **availabilityEstimate**, **available** và **priceSnapshot**, trường nào là sự thật hiện hành, trường nào là snapshot lịch sử, trường nào là dữ liệu dẫn xuất được phép trễ? Ai là nguồn có thẩm quyền?

### Phần B — Thiết kế event và version

Đề xuất event **RoomAvailabilityChanged** có:

~~~json
{
  "eventId": "evt-301",
  "aggregateId": "room:R-08:2026-12-01",
  "aggregateVersion": 21,
  "eventType": "RoomAvailabilityChanged",
  "payload": {
    "roomId": "R-08",
    "date": "2026-12-01",
    "available": false
  }
}
~~~

Giải thích cách consumer xử lý event v21 đến trước v20 và cách khác nhau giữa **full-state available=false** với **delta availableCount=-1**. Khi nhận duplicate v21, có được phát thêm một booking hay thay đổi số phòng khả dụng lần nữa không?

### Phần C — Bảo vệ điểm quyết định

Hai khách cùng thấy search báo phòng R-08 còn trống. Thiết kế đường **reserve/confirm nguyên tử tại Booking/Availability Authority** sao cho chỉ một yêu cầu có thể giữ cùng room/time slot. Vì sao việc chờ search cập nhật 5 giây không bảo đảm tính đúng?

### Phần D — Freshness và fallback

API ghi booking thành công và trả **committedVersion=21**, nhưng search mới ở 20. Nếu trang quản trị yêu cầu read-your-writes, hãy chọn đọc nguồn, chờ projection có timeout hoặc fallback. Nêu rõ cách tránh làm source quá tải khi toàn bộ consumer ngừng hoạt động.

### Phần E — Sự cố và đối soát

Tạo các tình huống:

~~~text
1. Commit booking thành công, API chết trước publish.
2. Event v21 được giao hai lần.
3. Event v22 (hủy) đến trước v21 (giữ phòng).
4. Search bị gián đoạn 2 phút.
5. Rebuild index khi người dùng vẫn đặt/hủy phòng.
6. Một booking đã hủy vẫn xuất hiện trong bản dẫn xuất.
~~~

Với mỗi tình huống, xác định **bằng chứng đúng**, cách phát hiện, cách phục hồi và ngưỡng thời gian lệch được phép. Cần kiểm tra cả trạng thái cuối và **lịch sử thao tác được báo thành công**.

### Gợi ý hướng giải

Customer Profile sở hữu tên/địa chỉ hiện hành; Booking giữ snapshot theo giao dịch đã chốt, không tự thay khi Profile đổi. Room Availability/Booking Authority quyết định giữ phòng nguyên tử. Search chỉ phục vụ **khám phá có thể trễ**; phải có event/CDC đáng tin, version theo aggregate, xử lý duplicate/reorder, tracking freshness và cơ chế fallback khi cần. Với bản dữ liệu xóa/hủy, phải đảm bảo event cũ không hồi sinh trạng thái đã bị loại bỏ.

**Kết luận:** Khi lặp dữ liệu trong NoSQL, hãy phân biệt **bản sao cần hội tụ** với **snapshot cố ý không thay đổi**. Bản sao cần hội tụ phải có **nguồn có thẩm quyền, đường phát thay đổi bền vững, version/idempotency, giới hạn độ lệch đo được và cơ chế đối soát**. Với các thao tác không được sai như thanh toán, đặt chỗ và phân quyền, **không giao quyền quyết định cho một bản đọc có thể stale**, dù freshness SLO của nó thường rất tốt.
