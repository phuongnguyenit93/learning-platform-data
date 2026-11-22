# Quan hệ giữa mô hình dữ liệu, đường truy cập, giao dịch và vận hành

Trong cơ sở dữ liệu NoSQL, thiết kế dữ liệu không kết thúc ở câu hỏi “lưu đối tượng này thành tài liệu hay thành nhiều bản ghi?”. Cách tổ chức dữ liệu quyết định ứng dụng có thể đọc bằng khóa nào, phải dùng chỉ mục gì, cần bao nhiêu lần truy cập mạng, cập nhật một nghiệp vụ có thể thực hiện nguyên tử hay không, và hệ thống sẽ phân phối tải như thế nào khi dữ liệu tăng.

Bốn yếu tố cần xem xét cùng nhau là **mô hình dữ liệu (data model)**, **đường truy cập (access path)**, **giao dịch và tính nhất quán (transaction and consistency)**, và **vận hành (operations)**. Thay đổi một yếu tố thường làm thay đổi chi phí hoặc độ phức tạp của các yếu tố còn lại.

## 1. Bốn góc nhìn của cùng một thiết kế

| Góc nhìn | Câu hỏi cốt lõi | Những quyết định điển hình |
|---|---|---|
| **Mô hình dữ liệu** | Dữ liệu nào nằm cùng nhau? Đâu là khóa và ranh giới của một thực thể nghiệp vụ? | Document, key–value, wide-column, graph; nhúng hay tham chiếu; chuẩn hóa hay nhân bản |
| **Đường truy cập** | Mỗi yêu cầu đọc/ghi sẽ tìm đúng dữ liệu bằng cách nào? | Partition key, sort key, chỉ mục phụ, materialized view, truy vấn theo cạnh, cache |
| **Giao dịch và nhất quán** | Điều gì bắt buộc phải đúng ngay sau khi ghi? Nhiều cập nhật liên quan được bảo vệ ra sao? | Atomic update, conditional write, transaction đa bản ghi, idempotency, saga, outbox |
| **Vận hành** | Thiết kế này hoạt động thế nào dưới tải lớn, lỗi máy và thay đổi dữ liệu? | Phân vùng, điểm nóng, replica, backup/restore, giám sát, migration, chi phí |

Một cách hình dung:

~~~mermaid
flowchart TD
    W["Workload và bất biến nghiệp vụ"] --> M["Mô hình dữ liệu"]
    W --> A["Đường truy cập"]
    W --> T["Giao dịch / nhất quán"]
    M <--> A
    M <--> T
    A <--> T
    M --> O["Vận hành: phân vùng, chỉ mục, độ trễ, phục hồi"]
    A --> O
    T --> O
    O --> R["Giới hạn và chi phí thực tế"]
    R --> M
    R --> A
    R --> T
~~~

Sơ đồ không mô tả một quy trình tuyến tính. Đó là **vòng lặp thiết kế**: từ nhu cầu truy cập và quy tắc đúng/sai của nghiệp vụ, chọn cách lưu và cập nhật; sau đó kiểm tra tải, chi phí, khả năng phục hồi rồi điều chỉnh.

### 1.1. Phân biệt mô hình logic với mô hình lưu trữ

Ở mức nghiệp vụ, hệ thống bán hàng có **Khách hàng**, **Đơn hàng**, **Sản phẩm**, **Tồn kho**. Các khái niệm này có thể liên hệ với nhau bất kể công nghệ cơ sở dữ liệu.

Ở mức lưu trữ, cùng một nghiệp vụ có thể được biểu diễn bằng:

- Một document đơn hàng chứa danh sách các dòng hàng.
- Một document tồn kho cho từng mã sản phẩm.
- Một tập dữ liệu phục vụ màn hình “đơn hàng của khách hàng”, được nhân bản từ đơn hàng gốc.
- Một luồng sự kiện dùng để cập nhật dữ liệu tổng hợp.

**Một thực thể nghiệp vụ không nhất thiết tương ứng một document, một collection hay một bảng**. Thiết kế vật lý phục vụ cách truy cập và bảo đảm tính đúng đắn của hệ thống.

### 1.2. “Đường truy cập” không phải đường dẫn API

API như **GET /customers/42/orders** nói ứng dụng cần gì. Đường truy cập của cơ sở dữ liệu nói máy chủ thực sự lấy các bản ghi bằng gì:

- Truy vấn trực tiếp theo khóa **customerId**?
- Đọc chỉ mục phụ **customerId + createdAt**?
- Lấy từ một bản sao danh sách đơn hàng đã sắp xếp?
- Quét tất cả đơn hàng rồi lọc theo khách hàng?

Bốn cách có thể trả về cùng dữ liệu nhưng khác rất lớn về độ trễ, chi phí và khả năng mở rộng. **Full scan** đôi khi hợp lý cho batch nhỏ hoặc tác vụ quản trị, nhưng thường không phù hợp với màn hình có lưu lượng cao và yêu cầu phản hồi nhanh.

## 2. Bắt đầu từ workload và bất biến, rồi mới chọn cấu trúc

Không nên bắt đầu bằng câu “NoSQL nên phi chuẩn hóa” hay “NoSQL không có giao dịch”. Cả hai đều quá chung. Đặc tính phụ thuộc vào họ cơ sở dữ liệu và sản phẩm cụ thể; một số hệ NoSQL hỗ trợ giao dịch nhiều document, một số đặt trọng tâm vào thao tác nguyên tử trên một mục hoặc một phân vùng.

Trước khi thiết kế, lập hai danh sách độc lập nhưng có liên quan.

**Danh sách truy cập** phải mô tả yêu cầu thực tế:

| Yêu cầu | Khóa tìm kiếm và sắp xếp | Tần suất / độ trễ | Độ mới cần thiết |
|---|---|---|---|
| Xem chi tiết đơn hàng | **orderId** | Rất thường xuyên; phản hồi nhanh | Thường cần nhìn thấy cập nhật mới nhất |
| Xem 20 đơn gần nhất của khách | **customerId**, giảm dần theo **createdAt** | Thường xuyên; phân trang | Có thể chấp nhận chậm vài giây nếu sản phẩm cho phép |
| Đặt hàng, giữ hàng trong kho | **sku**, số lượng cần giữ | Ghi đồng thời | Không được bán vượt tồn khả dụng |
| Tìm đơn theo trạng thái để xử lý | **status**, **updatedAt** | Công việc nền | Có thể xử lý theo lô |
| Thống kê doanh thu theo ngày | **date**, trạng thái thanh toán | Truy vấn tổng hợp | Có thể trễ theo lịch xử lý |

Cần bổ sung **khối lượng dữ liệu**, phân bố khóa (khách hàng hoặc sản phẩm nào quá nóng), tỷ lệ đọc/ghi, số bản ghi mỗi kết quả, kích thước mỗi bản ghi, yêu cầu phân trang, mức tăng trưởng và mục tiêu p95/p99. Ví dụ, “100.000 lần đọc/ngày” chưa đủ: 80% có thể dồn trong một giờ hoặc vào cùng một khách hàng.

**Danh sách bất biến nghiệp vụ** là những điều không được phép sai:

1. Tồn khả dụng của một SKU không được âm do hai người mua đồng thời.
2. Một yêu cầu đặt hàng được gửi lại vì mất kết nối không được tạo hai đơn hoặc trừ kho hai lần.
3. Trạng thái đơn hàng chỉ đi qua các chuyển trạng thái hợp lệ.
4. Màn hình lịch sử đơn có thể được phép hiển thị chậm hơn đơn gốc, nhưng chi tiết một đơn không được hiển thị trạng thái chưa được xác nhận như đã hoàn tất.

Sự khác biệt quan trọng: **độ mới của dữ liệu hiển thị** là một yêu cầu nhất quán; **không bán âm kho** là một bất biến cần cơ chế bảo vệ khi ghi. Cho phép một màn hình đọc dữ liệu trễ không đồng nghĩa được phép vi phạm bất biến.

## 3. Mô hình dữ liệu quyết định những đường truy cập nào rẻ

### 3.1. Document: tối ưu thao tác trên một khối dữ liệu thường đọc cùng nhau

Ví dụ document đơn hàng:

~~~json
{
  "orderId": "O-1042",
  "customerId": "C-27",
  "createdAt": "2026-11-14T08:00:00Z",
  "status": "PENDING",
  "items": [
    {"sku": "S-01", "quantity": 2, "unitPrice": 150000},
    {"sku": "S-07", "quantity": 1, "unitPrice": 230000}
  ],
  "total": 530000,
  "version": 1
}
~~~

Nếu màn hình chi tiết luôn cần các dòng hàng, nhúng **items** giúp lấy tất cả bằng một lần đọc document theo **orderId**. Giá tại thời điểm mua được lưu trong dòng đơn hàng để việc đổi giá sản phẩm sau này không làm đổi lịch sử.

Nhúng có giới hạn. Một mảng tăng vô hạn, ví dụ mọi sự kiện truy cập của một khách hàng, có thể khiến document quá lớn, tăng xung đột cập nhật và làm mỗi lần đọc/ghi tốn nhiều tài nguyên. Cần tách thành các bản ghi có khóa riêng hoặc chia theo thời gian.

### 3.2. Key–value: rất tốt nếu đã biết khóa chính

Ví dụ **order:O-1042 → document đơn hàng** cho phép truy cập trực tiếp. Nhưng nếu chỉ biết **customerId**, một kho key–value thuần túy không tự nhiên trả về “mọi đơn của khách, mới nhất trước”. Cần thêm một cấu trúc tra cứu hoặc hệ khác hỗ trợ truy vấn này.

### 3.3. Wide-column: thiết kế thứ tự dữ liệu theo khóa phân vùng

Một mô hình có thể tổ chức đơn theo khách:

~~~text
partition key: (customerId, monthBucket)
sort key:      (createdAt DESC, orderId)
value:         orderSummary
~~~

Truy vấn “20 đơn mới nhất của C-27 trong tháng này” trở nên phù hợp với cách dữ liệu được nhóm và sắp xếp. Tuy nhiên, truy vấn bằng **orderId** đơn lẻ cần một đường truy cập khác. Thêm **monthBucket** giúp giới hạn kích thước phân vùng, nhưng làm truy vấn nhiều tháng phải đọc và ghép nhiều phân vùng.

### 3.4. Graph: tối ưu duyệt quan hệ

Với các câu hỏi “bạn của bạn”, “các thực thể kết nối qua ba bước”, hay phát hiện các cụm liên quan, mô hình đỉnh–cạnh và phép duyệt có thể thích hợp hơn việc lặp đi lặp lại các truy vấn theo khóa. Đổi lại, cách phân phối dữ liệu đồ thị và truy vấn băng qua nhiều nút có thể là thách thức vận hành.

**Không có họ NoSQL nào mặc nhiên tốt hơn cho mọi đường truy cập.** Chọn dựa trên nhóm truy vấn quan trọng, ranh giới cập nhật và khả năng của hệ quản trị được triển khai.

## 4. Đường truy cập: khóa chính, chỉ mục, bản sao dữ liệu và chi phí ghi

### 4.1. Mỗi truy vấn quan trọng cần một đường đi dự kiến

Với màn hình chi tiết đơn theo **orderId**, đọc theo khóa chính là lựa chọn tự nhiên. Với lịch sử đơn theo **customerId**, có ba lựa chọn thường gặp:

| Giải pháp | Lợi ích | Chi phí và rủi ro |
|---|---|---|
| Chỉ mục phụ trên **customerId + createdAt** | Không cần ứng dụng tự quản lý bản sao; truy vấn theo thứ tự | Tăng dung lượng và chi phí ghi; tính nhất quán của chỉ mục tùy hệ |
| Bản sao / read model **OrdersByCustomer** | Có thể tối ưu riêng cho phân trang, lọc, hiển thị | Phải cập nhật đồng bộ hoặc bất đồng bộ; có thể trễ hoặc thiếu dữ liệu tạm thời |
| Quét collection rồi lọc | Dễ làm khi dữ liệu rất nhỏ | Đọc nhiều dữ liệu không cần thiết; khó giữ độ trễ ổn định khi tăng trưởng |

Một chỉ mục phụ cũng là dữ liệu cần duy trì: mỗi lần cập nhật trường được lập chỉ mục có thể phát sinh thêm công việc ghi và lưu trữ. Nhân bản dữ liệu thủ công cho một màn hình cũng có bản chất tương tự, nhưng ứng dụng phải tự chịu trách nhiệm duy trì nó.

### 4.2. Partition key ảnh hưởng trực tiếp đến phân phối tải

Khóa phân vùng quyết định các mục nằm gần nhau và các yêu cầu được chia cho các nút xử lý ra sao.

- Nếu khóa là **orderId** có độ phân tán tốt, tải chi tiết đơn thường trải trên nhiều khóa.
- Nếu khóa là một giá trị chung như **status = PENDING**, hàng triệu thao tác có thể dồn vào một nhóm khóa hoặc một phân vùng.
- Nếu một **customerId** có lưu lượng rất lớn, ngay cả khóa có nhiều giá trị phân biệt vẫn có thể tạo **hot partition**.
- Thêm hậu tố theo thời gian hoặc shard có thể phân tán ghi, nhưng truy vấn toàn bộ dữ liệu phải ghép kết quả từ nhiều nơi.

Vì vậy không thể đánh giá partition key chỉ bằng câu “trường này có unique hay không”. Cần nhìn cả **phân bố lưu lượng theo khóa** và các truy vấn cần dữ liệu nằm cùng nhau.

### 4.3. Đọc nhanh có thể làm ghi phức tạp

Giả sử một đơn hàng được lưu trong:

1. **OrdersById** để đọc chi tiết.
2. **OrdersByCustomer** để xem lịch sử.
3. **OrdersByStatus** để nhân viên xử lý.

Một lần cập nhật trạng thái đơn có thể đòi hỏi cập nhật ba cấu trúc. Nếu chúng nằm ở những khóa hoặc phân vùng khác nhau, không được tự giả định ba lần ghi luôn thành công đồng thời.

Đây là đánh đổi **read amplification** và **write amplification**:

- Ít bản sao: cập nhật đơn giản hơn, nhưng một lần đọc có thể phải kết hợp dữ liệu từ nhiều chỗ.
- Nhiều bản sao: đọc theo từng màn hình nhanh hơn, nhưng số ghi, dung lượng, độ trễ cập nhật và công việc phục hồi tăng.

Không cần nhân bản mọi dữ liệu. Với mỗi bản sao, hãy chỉ rõ **ai sở hữu dữ liệu gốc**, **bản sao phục vụ truy vấn nào**, **được phép trễ bao lâu**, và **cách tái tạo khi mất đồng bộ**.

## 5. Giao dịch gắn chặt với ranh giới dữ liệu

### 5.1. Atomicity trên một mục không có nghĩa atomicity trên toàn nghiệp vụ

Nhiều hệ document hoặc key–value có thao tác nguyên tử trên một document hoặc một mục. Một số hỗ trợ transaction trên nhiều document, collection hay phân vùng, nhưng **phạm vi, độ trễ, giới hạn kích thước, điều kiện triển khai và mức cách ly phải kiểm tra theo sản phẩm**.

Ví dụ cập nhật đồng thời **status** và **version** trong cùng document đơn hàng có thể được bảo vệ bằng một lần ghi nguyên tử:

~~~text
UPDATE order O-1042
SET status = "CONFIRMED", version = 2
ONLY IF status = "PENDING" AND version = 1
~~~

Đây là **mã giả**, không phải cú pháp dùng chung cho các NoSQL database. Điều kiện giúp hai tiến trình cùng đọc version 1 không thể cùng cập nhật thành công, với điều kiện cơ sở dữ liệu cung cấp compare-and-set / conditional write đúng nghĩa cho khóa đó.

Ngược lại, nếu đơn hàng và tồn kho nằm ở hai document hoặc hai hệ khác nhau, ghi cả hai **không tự động nguyên tử**. Không thể suy ra “đã lưu đơn” đồng nghĩa “đã giữ được hàng”.

### 5.2. Ranh giới aggregate nên đi theo bất biến

**Aggregate** là nhóm dữ liệu được xem như một đơn vị duy trì bất biến khi cập nhật. Nếu các dòng hàng, tổng tiền và trạng thái đơn luôn phải phù hợp với nhau tại thời điểm ghi, đặt chúng trong cùng một document có thể thuận lợi.

Nhưng không nên nhúng toàn bộ tồn kho của mọi SKU vào một đơn hàng. Một SKU được nhiều đơn cùng tham chiếu và cần cạnh tranh cập nhật. Nó có ranh giới sở hữu khác: **Inventory(SKU)**.

Điều cần xác định:

| Bất biến | Ranh giới có thể bảo vệ | Cơ chế |
|---|---|---|
| Tổng tiền khớp các dòng hàng khi tạo đơn | Một document đơn | Tính toán trước khi lưu; ghi nguyên tử |
| Không xác nhận cùng yêu cầu hai lần | Khóa idempotency hoặc bản ghi yêu cầu | Tạo có điều kiện; ràng buộc khóa duy nhất theo khả năng DB |
| Không giữ quá tồn khả dụng của một SKU | Bản ghi tồn kho theo SKU | Điều kiện **available >= quantity** và cập nhật nguyên tử |
| Đồng bộ lịch sử đơn với chi tiết đơn | Nhiều cấu trúc / read model | Transaction nếu hỗ trợ phù hợp, hoặc sự kiện + đối soát |

Nếu nhiều bất biến phải được bảo vệ đồng thời ở nhiều khóa, cần cân nhắc transaction đa mục với giới hạn thực tế, thiết kế lại ranh giới lưu trữ, hoặc quy trình nghiệp vụ có trạng thái trung gian.

### 5.3. Tính nhất quán khi đọc khác với tính nguyên tử khi ghi

Ba khái niệm không nên gộp làm một:

- **Atomicity**: một nhóm thay đổi hoặc xảy ra đầy đủ hoặc không xảy ra, trong phạm vi giao dịch được hỗ trợ.
- **Isolation / điều phối cạnh tranh**: các yêu cầu đồng thời tương tác với nhau ra sao; có ngăn mất cập nhật, ghi đè hoặc các bất thường phù hợp không.
- **Read consistency**: một lần đọc có thể quan sát dữ liệu mới nhất, dữ liệu từ replica chậm, hay một snapshot nào đó.

Một hệ có thể bảo đảm ghi nguyên tử cho một document nhưng đọc từ replica có độ trễ. Một hệ khác có transaction đa document nhưng vẫn yêu cầu lập chỉ mục hoặc cấp quyền truy vấn cụ thể để có đường đọc mong muốn. **Đọc nhất quán mạnh không thay thế kiểm tra cạnh tranh khi ghi**.

### 5.4. Khi một nghiệp vụ phải đi qua nhiều ranh giới

Ví dụ đặt hàng cần tạo đơn, giữ tồn kho và gửi yêu cầu thanh toán. Các hệ riêng biệt có thể không chia sẻ một transaction. Một **saga** tổ chức nhiều bước với trạng thái rõ ràng, retry an toàn và hành động bù khi thất bại.

~~~mermaid
stateDiagram-v2
    [*] --> PENDING: Nhận yêu cầu có idempotency key
    PENDING --> RESERVED: Giữ kho thành công
    PENDING --> REJECTED: Không đủ hàng
    RESERVED --> CONFIRMED: Thanh toán thành công
    RESERVED --> CANCELING: Thanh toán thất bại / hết hạn
    CANCELING --> CANCELED: Đã trả lại số lượng giữ
    CONFIRMED --> [*]
    REJECTED --> [*]
    CANCELED --> [*]
~~~

Đây là luồng khái niệm; triển khai thực tế còn cần trạng thái timeout, retry và đối soát. Các sự kiện có thể đến lặp lại hoặc lệch thứ tự, vì vậy handler nên:

- Nhận diện **idempotency key / eventId** để xử lý lặp không tạo tác dụng phụ mới.
- Dùng điều kiện trạng thái hoặc version để chặn chuyển trạng thái cũ ghi đè trạng thái mới.
- Ghi nhận trạng thái trung gian đủ lâu để phục hồi khi tiến trình chết giữa chừng.
- Có quy trình xử lý các yêu cầu “đang giữ kho” bị treo hoặc quá hạn.

**Transactional outbox** có thể giúp ghi thay đổi nghiệp vụ cùng một thông điệp chờ phát trong **cùng ranh giới nguyên tử**. Một tiến trình sau đó phát thông điệp ra broker. Nếu cơ sở dữ liệu không hỗ trợ ghi nguyên tử cho cả dữ liệu nghiệp vụ và outbox ở cấu trúc đã chọn, cần cơ chế khác như event log cùng document, CDC phù hợp hoặc thiết kế lại luồng; không thể chỉ thêm bảng outbox rồi tự nhiên có bảo đảm.

Outbox chủ yếu giải quyết rủi ro **đã commit dữ liệu nhưng chưa phát được sự kiện**. Nó không mặc nhiên bảo đảm mỗi sự kiện chỉ được giao đúng một lần; consumer vẫn cần idempotency.

## 6. Case study: thiết kế NoSQL cho hệ thống đơn hàng

Giả sử có bốn yêu cầu: xem chi tiết đơn thật nhanh, xem danh sách đơn của từng khách theo thời gian, giữ kho đúng khi có nhiều người đặt cùng một sản phẩm, và chạy báo cáo cuối ngày. Ta không chọn công nghệ cụ thể để tập trung vào lập luận.

### 6.1. Thiết kế đề xuất theo từng nhu cầu

| Nhu cầu | Dữ liệu và đường truy cập | Yêu cầu giao dịch | Tác động vận hành |
|---|---|---|---|
| Chi tiết đơn | **OrdersById(orderId)**, document có **items** | Ghi/chuyển trạng thái nguyên tử trong đơn | Trải tải theo orderId; theo dõi kích thước document |
| Lịch sử khách | Chỉ mục hoặc **OrdersByCustomer(customerId, createdAt)** | Có thể cập nhật bất đồng bộ nếu UI cho phép | Theo dõi độ trễ projection và phân vùng khách quá nóng |
| Giữ kho | **Inventory(sku)**, điều kiện giảm **available** | Conditional update nguyên tử cho từng SKU; quy trình nhiều SKU cần thiết kế riêng | SKU bán chạy tạo điểm nóng; đo conflict/retry |
| Công việc theo trạng thái | Chỉ mục phù hợp hoặc hàng đợi tác vụ | Handler an toàn khi nhận trùng | Tránh quét định kỳ toàn bộ đơn |
| Báo cáo ngày | Projection tổng hợp / hệ phân tích | Độ mới theo lịch; không nằm trên luồng checkout | Batch/stream, chi phí lưu trữ và backfill |

**OrdersByCustomer** có thể chỉ chứa **orderId, createdAt, status, total** thay vì nhân bản toàn bộ đơn. Khi người dùng mở chi tiết, ứng dụng tải đơn gốc từ **OrdersById**. Cách này giảm dữ liệu nhân bản nhưng có thể cần thêm lần đọc khi mở chi tiết.

### 6.2. Luồng đặt hàng không bán quá số lượng

Giả sử **Inventory(S-01)** có **available = 5**. Hai khách đồng thời mua 4 và 3 sản phẩm. Cả hai cùng đọc “còn 5” rồi tự trừ là không an toàn.

Thao tác cần được kiểm tra và cập nhật như **một hành động nguyên tử** tại nơi sở hữu tồn kho:

~~~text
reserve(sku = "S-01", quantity = 4, reservationId = "R-1"):
    nếu reservationId đã xử lý:
        trả kết quả cũ
    chỉ khi available >= 4:
        available = available - 4
        lưu reservation "R-1" với số lượng 4
    nếu điều kiện không đạt:
        trả INSUFFICIENT_STOCK
~~~

Điểm then chốt là kiểm tra điều kiện, trừ tồn và ghi nhận reservation phải được triển khai với **bảo đảm nguyên tử phù hợp**. Mã giả chỉ mô tả nghiệp vụ; nếu reservation và inventory nằm ở hai khóa mà DB không hỗ trợ transaction tương ứng, cần đổi mô hình hoặc dùng cơ chế đảm bảo khác. Với giỏ có nhiều SKU, mỗi SKU cập nhật riêng **không tạo ra một transaction toàn giỏ**. Saga có thể giữ từng SKU rồi trả lại các phần đã giữ khi có SKU thất bại, hoặc dùng transaction đa khóa nếu đáp ứng được quy mô và tính năng DB.

Một luồng phối hợp có thể thực hiện như sau:

1. Nhận yêu cầu với **requestId** cố định; kiểm tra hoặc tạo đơn **PENDING** một cách idempotent.
2. Phát công việc giữ kho qua cơ chế truyền sự kiện bền vững gắn với cập nhật đơn.
3. Dịch vụ kho thử giữ từng mặt hàng với điều kiện nguyên tử và reservationId; trả kết quả.
4. Nếu giữ thành công, tiếp tục thanh toán và chuyển đơn sang **CONFIRMED** theo điều kiện trạng thái/version.
5. Nếu thất bại hoặc hết hạn, chuyển sang hủy và trả các reservation đã giữ; tác vụ bù cũng phải idempotent.
6. Cập nhật chỉ mục/projection **OrdersByCustomer**; màn hình chi tiết lấy trạng thái có thẩm quyền từ **OrdersById**.

Khi máy chủ chết sau bước giữ hàng nhưng trước khi đơn nhận sự kiện, hệ thống cần **retry, thời hạn giữ, truy vết reservation và đối soát**. Đây là yêu cầu vận hành xuất phát trực tiếp từ việc đơn và kho không thuộc cùng một ranh giới giao dịch.

### 6.3. Lập luận về đánh đổi

**Phương án A — chỉ một bản ghi đơn, không có read model:** ít ghi và đơn giản hơn; truy vấn lịch sử theo khách có thể cần chỉ mục. Nếu hệ quản trị có chỉ mục phù hợp, đây có thể là phương án tốt.

**Phương án B — thêm OrdersByCustomer:** đáp ứng truy vấn danh sách được tối ưu riêng và cho phép thay đổi hình thức hiển thị; đổi lại phải xử lý độ trễ, dữ liệu trùng và tái tạo projection.

**Phương án C — đặt mọi dữ liệu khách, đơn, kho vào một document lớn:** có thể giảm số lần đọc trong một số màn hình, nhưng xung đột ghi, document tăng không giới hạn và quyền sở hữu tồn kho chung giữa nhiều khách khiến mô hình khó vận hành và khó giữ bất biến.

Lựa chọn phụ thuộc vào tải, đường truy cập chính, khả năng transaction/index của sản phẩm và mức phức tạp ứng dụng có thể chấp nhận.

## 7. Các hệ quả vận hành phải tính ngay trong thiết kế

### 7.1. Hot key và hot partition

Nếu một sản phẩm đang được flash sale, hàng nghìn request có thể cùng cập nhật **Inventory(S-01)**. Dù các đơn hàng khác được phân tán đều, tồn kho SKU đó vẫn có thể là điểm nóng.

Một số hướng xử lý, mỗi hướng có điều kiện áp dụng:

- **Giới hạn tốc độ / xếp hàng** theo SKU để kiểm soát cạnh tranh.
- **Optimistic concurrency / conditional update** để giữ đúng bất biến, chấp nhận retry và conflict.
- **Phân bổ quota theo nhiều bucket** nếu có cơ chế cấp phát và tổng hợp quota bảo đảm không vượt tổng tồn; chỉ chia khóa ngẫu nhiên mà không điều phối là không đủ.
- **Đổi cách mở bán** như queue hoặc phân phối suất theo đợt để giảm đỉnh ghi.

Không có một partition key “đẹp” nào tự loại bỏ mọi điểm nóng khi một tài nguyên thực sự là điểm tranh chấp tập trung.

### 7.2. Chỉ mục, nhân bản và tổng chi phí

Giả sử giả định để ước lượng: một triệu đơn/ngày, mỗi document gốc trung bình 1 KB. Dữ liệu gốc mới phát sinh khoảng **1 GB/ngày** theo đơn vị thập phân, chưa kể metadata. Nếu bản sao phục vụ lịch sử chiếm 0,25 KB/đơn, phần đó tăng thêm khoảng **0,25 GB/ngày**.

Con số này **chưa gồm** index overhead, replication, version cũ, log, nén, backup và sự khác biệt giữa kích thước logic với dung lượng tính phí. Dù vậy nó cho thấy một quyết định làm truy vấn nhanh hơn cũng làm phát sinh chi phí lưu trữ và ghi theo tốc độ tăng dữ liệu.

Khi lập capacity plan, cần tính cả:

~~~text
tổng tải ghi ≈ ghi dữ liệu gốc
             + cập nhật chỉ mục
             + cập nhật các read model
             + ghi log / sự kiện phục vụ đồng bộ
~~~

Đây là công thức tư duy, không phải công thức tính billing cho mọi nhà cung cấp. Các thành phần có thể được xử lý nội bộ hoặc bất đồng bộ tùy hệ quản trị.

### 7.3. Replication, failover và tính nhất quán quan sát được

Replica giúp chịu lỗi và có thể tăng khả năng phục vụ đọc, nhưng cần biết **chính sách ghi, acknowledgment, đọc từ leader hay follower, replication lag và failover**. Sau khi người dùng vừa xác nhận đơn:

- Đọc từ một replica trễ có thể vẫn thấy **PENDING**.
- Đọc từ nguồn có thẩm quyền hoặc dùng cơ chế đọc phù hợp có thể cần thiết với trang xác nhận.
- Read model bất đồng bộ có thể chưa có đơn mới trong lịch sử dù đơn gốc đã tồn tại.

Ứng dụng có thể dùng thông báo “đơn đang được xử lý”, chờ projection bắt kịp, hoặc đọc trực tiếp đơn gốc cho phần hiển thị cần mới nhất. Phải xác định kỳ vọng của người dùng, thay vì gọi chung mọi trường hợp là “eventual consistency”.

### 7.4. Backup, restore và rebuild

Với nhiều bản sao dữ liệu, câu hỏi phục hồi không chỉ là “restore collection nào?” mà còn:

- Nguồn dữ liệu có thẩm quyền là gì?
- Nếu restore đơn gốc về một mốc thời gian, bản sao lịch sử và báo cáo phải đồng bộ về mốc nào?
- Có thể phát lại sự kiện hoặc quét nguồn để dựng lại projection không?
- Đối soát làm sao để phát hiện order thiếu trong danh sách, reservation hết hạn chưa trả, hay sự kiện xử lý trùng?

**RPO** (mức dữ liệu có thể mất) và **RTO** (thời gian phục hồi mục tiêu) phải được hiểu theo **toàn bộ luồng nghiệp vụ**, không chỉ thao tác khôi phục một node cơ sở dữ liệu.

### 7.5. Thay đổi schema trên dữ liệu đang chạy

NoSQL thường cho phép cấu trúc document linh hoạt hơn, nhưng điều đó không xóa bỏ công việc migration.

Ví dụ thêm **currency** vào đơn hàng:

1. Phiên bản đọc mới xử lý được cả document cũ chưa có **currency**.
2. Phiên bản ghi mới bắt đầu lưu **currency**.
3. Nếu cần, chạy backfill có kiểm soát cho dữ liệu cũ.
4. Giám sát lỗi đọc, tốc độ backfill, tác động lên throughput và các read model.
5. Chỉ bỏ logic tương thích cũ sau khi đã xác nhận các luồng dùng dữ liệu mới.

Khi đổi partition key hay sort key, có thể phải xây collection/bảng mới và chuyển dữ liệu. Tính linh hoạt về schema **không đồng nghĩa thay đổi khóa truy cập không có chi phí**.

### 7.6. Những chỉ số nên quan sát

| Nhóm | Chỉ số và dấu hiệu |
|---|---|
| Đường đọc | p95/p99 latency theo truy vấn, số bản ghi được đọc so với số bản ghi trả về, index miss, scan |
| Đường ghi | Write latency, conditional write conflict, retry, throttle, số ghi do chỉ mục/projection |
| Phân vùng | Request và dung lượng theo khóa/phân vùng, hot key, mất cân bằng tải |
| Nhất quán | Replication lag, projection lag, số sự kiện chưa xử lý, số tác vụ bù tồn đọng |
| Độ tin cậy | Tỷ lệ lỗi, timeout, backup/restore drill, reconciliation mismatch |
| Chi phí | Dung lượng gốc/bản sao/chỉ mục, request units hoặc I/O, băng thông và backup |

Chỉ số tổng trung bình có thể che mất điểm nóng. Ví dụ throughput toàn cụm còn dư không bảo đảm một SKU được cập nhật liên tục không bị throttling.

## 8. Các sai lầm tư duy thường gặp

### “Dữ liệu NoSQL không cần quan hệ”

Dữ liệu vẫn có quan hệ nghiệp vụ. NoSQL có thể thể hiện quan hệ bằng nhúng, tham chiếu, chỉ mục, bản sao hoặc cạnh đồ thị. Câu hỏi là **biểu diễn quan hệ để phục vụ truy cập và bất biến nào**, không phải xóa bỏ quan hệ.

### “Nhúng tất cả sẽ nhanh vì chỉ đọc một lần”

Chỉ đúng với khối dữ liệu có kích thước và vòng đời hợp lý, thường đọc/cập nhật cùng nhau. Nhúng danh sách tăng vô hạn hoặc nhiều thực thể cùng bị ghi có thể tạo document quá lớn và tranh chấp.

### “Thêm index là giải quyết mọi truy vấn”

Chỉ mục không loại bỏ hoàn toàn chi phí ghi, phân trang, tính chọn lọc thấp hoặc phân phối tải mất cân bằng. Có truy vấn cần precompute hoặc đổi cách tương tác sản phẩm; có truy vấn tốt hơn nên chạy qua hệ phân tích.

### “Eventual consistency nghĩa là lúc nào cũng có thể trả dữ liệu cũ”

Không. Từng luồng có mức chấp nhận khác nhau. Báo cáo ngày có thể trễ; xác nhận số lượng tồn kho hay ngăn xử lý trùng phải bảo vệ bằng cơ chế ghi phù hợp. Độ trễ projection không phải lý do để bỏ kiểm soát bất biến.

### “Có transaction là không cần idempotency”

Giao dịch bảo vệ các cập nhật trong phạm vi của nó. Client timeout có thể khiến cùng request được gửi lại; message broker có thể giao lại một thông điệp. **Idempotency** xử lý tác động lặp ở cấp yêu cầu và công việc nền.

### “Đã chạy tốt ở dữ liệu nhỏ thì mô hình đúng”

Một full scan trên vài nghìn record có thể rất nhanh. Khi số bản ghi, chỉ mục, số tenant, lượng ghi hoặc tỷ lệ khách hàng nóng tăng, đường truy cập và phân vùng quyết định hệ thống còn đáp ứng SLO hay không.

## 9. Quy trình ra quyết định cho một bài toán NoSQL

Khi thiết kế một chức năng mới, có thể đi theo trình tự:

1. **Liệt kê thao tác đọc/ghi**: khóa nào biết sẵn, cần lọc/sắp xếp thế nào, số kết quả, tần suất, độ trễ mục tiêu.
2. **Định nghĩa bất biến**: điều gì phải đúng trong cùng một lần cập nhật; cái gì được phép trễ và trong bao lâu.
3. **Xác định nguồn dữ liệu có thẩm quyền và aggregate**: dữ liệu nào thay đổi cùng nhau, đâu là ranh giới tranh chấp.
4. **Vẽ đường truy cập** cho mỗi truy vấn quan trọng: khóa chính, chỉ mục, read model hoặc bước truy vấn qua nhiều nguồn; ghi rõ số lần truy cập dự kiến.
5. **Chọn cơ chế cạnh tranh và giao dịch** phù hợp với phạm vi hỗ trợ thực tế: conditional write, transaction, idempotency, saga, outbox.
6. **Kiểm tra phân bố tải và vận hành**: hot keys, tài liệu quá lớn, chi phí chỉ mục, replica lag, phục hồi, backfill, giám sát.
7. **Thử nghiệm trên workload đại diện**: không chỉ tổng requests/second mà cả skew theo khóa, số lượng mục trong phân vùng, p95/p99, lỗi retry, thời gian dựng lại projection.
8. **Lặp lại thiết kế** nếu một đường truy cập nhanh kéo theo giao dịch quá phức tạp hoặc một ranh giới giao dịch thuận tiện tạo điểm nóng không chấp nhận được.

Có thể ghi lại các quyết định dưới dạng ma trận:

| Access pattern / invariant | Model và khóa | Cơ chế nhất quán | Tác động vận hành |
|---|---|---|---|
| Ví dụ: xem 20 đơn gần nhất | **OrdersByCustomer(customerId, createdAt)** | Projection có thể trễ tối đa theo SLO đã định | Theo dõi lag, phân trang, hot customer |
| Ví dụ: không bán âm kho | **Inventory(sku)** | Conditional update/transaction đúng phạm vi | Theo dõi conflict, hot SKU, reservation treo |

Ma trận ép mỗi quyết định lưu trữ trả lời đủ bốn câu hỏi, giúp nhìn thấy đánh đổi trước khi triển khai.

## 10. Câu hỏi tự luyện

**Bài 1.** Một ứng dụng lưu tất cả bình luận của bài viết trong một mảng bên trong document bài viết. Bài nổi tiếng có hàng triệu bình luận. Hãy chỉ ra ảnh hưởng đến đường đọc, cập nhật đồng thời, kích thước document và vận hành. Đề xuất cách phân trang bằng khóa thích hợp.

**Bài 2.** Một dịch vụ dùng **OrdersById** và bản sao **OrdersByCustomer** cập nhật qua sự kiện. Người dùng đặt hàng thành công nhưng lập tức không thấy đơn trong danh sách. Đây nhất thiết là mất dữ liệu hay không? Thiết kế hành vi UI, chiến lược đọc và chỉ số theo dõi độ trễ.

**Bài 3.** Hai người cùng mua sản phẩm có tồn cuối cùng là 1. Hãy mô tả vì sao quy trình “đọc số lượng → trừ trong ứng dụng → ghi lại” có thể bán quá tồn, và xác định chính xác thao tác nào phải được bảo vệ nguyên tử.

**Bài 4.** Hệ thống lưu lịch sử hoạt động theo **tenantId**. Một tenant chiếm 70% ghi. Đề xuất cách đổi partition key để giảm điểm nóng và nêu chi phí phải trả khi truy vấn lịch sử toàn tenant theo thời gian.

Gợi ý khi tự đối chiếu: một phương án được xem là có cơ sở khi đồng thời chỉ rõ **đường truy cập thực tế**, **bất biến được bảo vệ bằng cơ chế nào**, **điểm có thể trễ hoặc thất bại**, và **cách hệ thống phát hiện, phục hồi sai lệch**.

---

**Kết luận:** Trong tư duy NoSQL, dữ liệu được tổ chức theo cách ứng dụng truy cập; cách tổ chức ấy đặt ra ranh giới giao dịch; còn ranh giới giao dịch và các bản sao dữ liệu quyết định nhiều vấn đề vận hành. Thiết kế tốt là thiết kế cân bằng cả bốn yếu tố theo workload và mức đúng đắn mà nghiệp vụ thực sự cần.
