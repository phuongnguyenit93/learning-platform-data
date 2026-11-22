# Phân rã nghiệp vụ thành function và dịch vụ có ranh giới rõ ràng

Trong chương **Thiết kế kiến trúc serverless**, quyết định quan trọng không phải là tạo bao nhiêu function, mà là chia hệ thống theo những trách nhiệm nghiệp vụ nào và đặt ranh giới dữ liệu ở đâu. Một function FaaS là đơn vị thực thi được gọi bởi HTTP, thông điệp hoặc sự kiện. Một service là đơn vị sở hữu một năng lực nghiệp vụ, quy tắc và dữ liệu liên quan. Một service có thể chứa nhiều function; vì vậy không nên xem mỗi function là một microservice độc lập.

Bài học này thuộc module **CLOUD_SERVERLESS**, tập trung vào phát triển và triển khai ứng dụng serverless, đặc biệt là Java function được kích hoạt bởi HTTP, thông điệp hoặc sự kiện. Các quyết định phân rã cần tính đến trạng thái, quyền truy cập, retry, idempotency, cold start, khả năng mở rộng và chi phí vận hành. Mục tiêu là tạo ra các ranh giới đủ rõ để từng phần có thể phát triển và vận hành độc lập mà không làm luồng nghiệp vụ trở nên rời rạc.

## 1. Phân biệt năng lực nghiệp vụ, service và function

Trước khi chia hệ thống, cần thống nhất ba khái niệm:

| Khái niệm | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Năng lực nghiệp vụ (business capability) | Hệ thống cần làm được việc gì cho tổ chức hoặc người dùng? | Quản lý đơn hàng, quản lý tồn kho, xử lý thanh toán |
| Service / bounded context | Phần nghiệp vụ nào sở hữu quy tắc, dữ liệu và hợp đồng riêng? | Order Service sở hữu vòng đời đơn hàng |
| Function | Đoạn xử lý nào được kích hoạt bởi một trigger cụ thể? | Hàm nhận HTTP tạo đơn, hàm xử lý sự kiện đơn hàng mới |

Một function thường thực hiện một bước xử lý có đầu vào và đầu ra rõ ràng. Nó có thể được triển khai riêng, mở rộng theo số lần gọi và cấp quyền theo nhu cầu. Service gom các function có cùng ngữ cảnh nghiệp vụ, cùng quyền sở hữu dữ liệu và cùng một tập hợp quy tắc.

Ví dụ, Order Service có thể gồm:

- Function nhận yêu cầu HTTP để tạo đơn hàng.
- Function nhận HTTP để truy vấn trạng thái đơn hàng.
- Function xử lý sự kiện thanh toán thành công.
- Function xử lý yêu cầu hủy đơn từ hàng đợi.

Các function này có trigger và đặc tính vận hành khác nhau, nhưng cùng làm việc với vòng đời đơn hàng. Chúng vẫn thuộc một ranh giới nghiệp vụ vì cùng chịu trách nhiệm về trạng thái và quy tắc của đơn hàng.

Ngược lại, một function không nên được tách thành service riêng chỉ vì nó có một endpoint hoặc một lớp Java riêng. Ranh giới service phải xuất phát từ trách nhiệm nghiệp vụ, quyền sở hữu dữ liệu và mức độ độc lập cần có.

## 2. Nguyên tắc xác định ranh giới

### 2.1. Chia theo năng lực nghiệp vụ, không chia theo tầng kỹ thuật

Một cách chia thường gặp nhưng dễ gây phụ thuộc là tạo các service như UserController, OrderRepository hoặc PaymentDatabase. Đây là cách chia theo tầng kỹ thuật. Khi một quy trình nghiệp vụ cần đi qua nhiều tầng ở nhiều service, thay đổi nhỏ cũng có thể buộc nhiều nhóm cùng sửa và triển khai.

Nên bắt đầu bằng câu hỏi: “Năng lực nghiệp vụ nào cần được quản lý độc lập?”. Ví dụ:

- Order chịu trách nhiệm tiếp nhận đơn, quản lý trạng thái và các quy tắc vòng đời đơn.
- Inventory chịu trách nhiệm số lượng có thể bán, giữ chỗ và hoàn trả tồn kho.
- Payment chịu trách nhiệm yêu cầu thanh toán, kết quả giao dịch và đối soát.
- Notification chịu trách nhiệm chuyển thông tin đến email, SMS hoặc kênh thông báo khác.

Tên service nên diễn đạt được một trách nhiệm nghiệp vụ. Nếu tên chỉ mô tả công nghệ hoặc một bảng dữ liệu, cần xem lại ranh giới.

### 2.2. Dữ liệu và quy tắc phải có chủ sở hữu

Mỗi service nên là nơi có thẩm quyền thay đổi dữ liệu nghiệp vụ của chính nó. Service khác truy cập dữ liệu qua API hoặc nhận sự kiện đã công bố, thay vì ghi trực tiếp vào bảng của service đó.

Ví dụ, Inventory sở hữu số lượng tồn và quy tắc giữ hàng. Order không tự giảm số lượng trong cơ sở dữ liệu tồn kho. Order gửi yêu cầu giữ hàng hoặc phát sự kiện OrderPlaced; Inventory quyết định có thể giữ hàng hay không rồi phản hồi bằng kết quả.

Quyền sở hữu dữ liệu giúp trả lời rõ:

- Service nào được phép tạo, sửa hoặc chuyển trạng thái của dữ liệu?
- Quy tắc nào phải được bảo vệ trong cùng một giao dịch?
- Service khác cần thông tin gì để tiếp tục quy trình?
- Nếu dữ liệu thay đổi, service nào chịu trách nhiệm phát thông tin cập nhật?

“Database per service” là một nguyên tắc về quyền sở hữu logic. Ở hệ thống nhỏ, nhiều service có thể dùng chung một cụm cơ sở dữ liệu vật lý, nhưng vẫn cần schema, quyền ghi và hợp đồng truy cập tách biệt. Dùng chung máy chủ không đồng nghĩa với việc service khác được truy cập trực tiếp vào bảng nội bộ.

### 2.3. Giữ các bất biến nghiệp vụ trong cùng ranh giới

Bất biến (invariant) là điều kiện phải luôn đúng đối với dữ liệu nghiệp vụ. Ví dụ:

- Tổng số tiền của các dòng hàng phải khớp với tổng tiền đơn hàng theo chính sách tính giá.
- Một đơn không thể được xác nhận thanh toán hai lần.
- Số lượng tồn có thể bán không được âm.
- Một giao dịch thanh toán không được chuyển từ trạng thái đã hoàn tiền trở lại đã thanh toán.

Nếu hai thao tác luôn phải cùng thành công hoặc cùng thất bại để giữ một bất biến, chúng thường nên nằm trong cùng một service và một ranh giới giao dịch. Đưa chúng sang hai service khác nhau sẽ biến giao dịch cục bộ thành quy trình phân tán, cần cơ chế bù trừ và xử lý trạng thái trung gian.

Không phải mọi bước của một quy trình đều phải nằm trong cùng service. Chỉ những quy tắc cần tính nhất quán tức thời mới cần ở cùng ranh giới. Các bước có thể hoàn tất sau, như gửi email xác nhận, phù hợp với xử lý bất đồng bộ.

### 2.4. Giảm phụ thuộc đồng bộ giữa các service

Một function gọi đồng bộ nhiều service khác có thể tạo thành chuỗi phụ thuộc:

**HTTP → Order → Inventory → Pricing → Customer → Payment**

Nếu một service chậm hoặc lỗi, toàn bộ yêu cầu có thể chậm hoặc thất bại. Chuỗi gọi dài còn làm tăng độ trễ, chi phí truyền dữ liệu và độ phức tạp khi retry.

Chỉ nên gọi đồng bộ khi bên gọi thực sự cần kết quả ngay để trả lời yêu cầu hiện tại. Nếu bước tiếp theo có thể xử lý sau, hãy cân nhắc gửi message hoặc phát event. Giao tiếp bất đồng bộ giúp giảm phụ thuộc thời gian chạy, nhưng đổi lại hệ thống phải chấp nhận trạng thái trung gian và eventual consistency.

### 2.5. Giữ function không phụ thuộc trạng thái của lần gọi trước

FaaS có thể chạy nhiều instance đồng thời, tái sử dụng hoặc tạo mới môi trường thực thi. Một lần gọi không nên phụ thuộc vào biến trong bộ nhớ của lần gọi trước. Dữ liệu cần tồn tại qua nhiều lần gọi phải được lưu trong cơ sở dữ liệu, object storage, cache hoặc hệ thống quản lý trạng thái phù hợp.

Có thể tái sử dụng client kết nối hoặc cấu hình bất biến trong vòng đời instance để giảm chi phí khởi tạo. Tuy nhiên, không được xem biến toàn cục hay bộ nhớ instance là nơi lưu trạng thái nghiệp vụ đáng tin cậy.

## 3. Quy trình phân rã từ nghiệp vụ đến function

Có thể áp dụng quy trình sau cho một hệ thống mới hoặc khi chuyển một ứng dụng hiện có sang serverless.

### Bước 1: Mô tả luồng nghiệp vụ đầu cuối

Bắt đầu bằng một hành trình có ý nghĩa với người dùng hoặc tổ chức, thay vì bắt đầu từ danh sách endpoint hay bảng dữ liệu.

Ví dụ luồng mua hàng:

1. Người dùng gửi yêu cầu đặt hàng.
2. Hệ thống kiểm tra thông tin và ghi nhận đơn.
3. Hệ thống giữ số lượng hàng.
4. Hệ thống yêu cầu thanh toán.
5. Hệ thống xác nhận hoặc từ chối đơn.
6. Hệ thống gửi thông báo cho người dùng.

Với mỗi bước, ghi lại tác nhân, dữ liệu đầu vào, kết quả mong muốn, lỗi có thể xảy ra và bước nào cần kết quả ngay.

### Bước 2: Nhóm các hoạt động theo năng lực nghiệp vụ

Nhóm những hoạt động cùng sử dụng một ngôn ngữ nghiệp vụ và cùng chịu trách nhiệm về một tập quy tắc. Trong ví dụ trên, quản lý đơn hàng, giữ tồn kho, xử lý thanh toán và gửi thông báo là các năng lực khác nhau.

Một nhóm hợp lý thường có các dấu hiệu:

- Có mục tiêu nghiệp vụ rõ ràng.
- Có dữ liệu và quy tắc mà nhóm đó chịu trách nhiệm.
- Có thể mô tả hợp đồng với các nhóm khác.
- Có lý do thực tế để thay đổi, triển khai hoặc mở rộng độc lập.

Nếu hai nhóm liên tục phải thay đổi cùng nhau, chia sẻ cùng bất biến hoặc gọi nhau đồng bộ ở hầu hết thao tác, ranh giới có thể đang bị tách quá nhỏ.

### Bước 3: Xác định dữ liệu sở hữu và ranh giới giao dịch

Liệt kê thực thể, trạng thái và quy tắc quan trọng của từng năng lực. Đánh dấu service sở hữu từng dữ liệu. Sau đó xác định thao tác nào phải được thực hiện nguyên tử.

Ví dụ:

| Dữ liệu / quy tắc | Service sở hữu | Lý do |
|---|---|---|
| Mã đơn, dòng hàng, trạng thái đơn | Order | Quản lý vòng đời đơn |
| Số lượng khả dụng, giữ chỗ tồn kho | Inventory | Bảo vệ quy tắc tồn kho |
| Mã giao dịch, trạng thái thanh toán | Payment | Theo dõi kết quả giao dịch |
| Trạng thái gửi email, lịch sử thông báo | Notification | Quản lý việc chuyển thông tin |

Một service có thể lưu bản chụp dữ liệu cần thiết cho nghiệp vụ của mình. Chẳng hạn, Order lưu tên và giá tại thời điểm đặt hàng để hóa đơn không thay đổi khi thông tin sản phẩm được cập nhật. Bản chụp này không biến Order thành chủ sở hữu dữ liệu danh mục sản phẩm.

### Bước 4: Chọn giao tiếp đồng bộ hay bất đồng bộ

Phân loại từng tương tác:

- **Đồng bộ** khi cần câu trả lời ngay, ví dụ kiểm tra quyền truy cập hoặc trả kết quả truy vấn.
- **Bất đồng bộ** khi có thể xử lý sau, cần tách thời gian sống của bên gửi và bên nhận, hoặc có nhiều bên quan tâm đến một sự kiện.
- **Kết hợp** khi yêu cầu cần xác nhận đã tiếp nhận ngay, còn quy trình dài được xử lý nền.

Không nên chuyển mọi lời gọi thành event. Nếu người dùng cần biết ngay một dữ liệu có hợp lệ hay không, một lời gọi đồng bộ có timeout và xử lý lỗi rõ ràng có thể phù hợp hơn. Ngược lại, không nên giữ kết nối HTTP trong lúc chờ một quy trình kéo dài nếu có thể trả về mã theo dõi và xử lý nền.

### Bước 5: Đặt service boundary trước, sau đó mới chọn function

Sau khi có các nhóm nghiệp vụ và quyền sở hữu dữ liệu, xác định các điểm vào của từng service. Mỗi điểm vào có thể trở thành một function riêng nếu cần trigger, quyền truy cập, khả năng mở rộng hoặc vòng đời triển khai khác nhau.

Ví dụ Order Service có thể có:

| Function | Trigger | Trách nhiệm |
|---|---|---|
| PlaceOrderFunction | HTTP POST | Kiểm tra yêu cầu và khởi tạo đơn |
| GetOrderFunction | HTTP GET | Trả thông tin đơn theo quyền truy cập |
| PaymentResultFunction | Event | Cập nhật đơn theo kết quả thanh toán |
| CancelOrderFunction | Message | Xử lý yêu cầu hủy đơn đã được chấp nhận |

Không cần tạo một function cho từng câu lệnh hoặc từng phương thức nội bộ. Một function có thể gọi nhiều lớp trong cùng service để thực hiện một ca sử dụng. Việc chia nhỏ nên có lợi ích cụ thể về trigger, quyền, mở rộng, cô lập lỗi hoặc triển khai.

### Bước 6: Định nghĩa hợp đồng giữa các ranh giới

Với API, xác định đường dẫn, phương thức, schema, mã lỗi, timeout và cách xác thực. Với message hoặc event, xác định tên, phiên bản schema, định danh, thời điểm phát và ý nghĩa nghiệp vụ.

Phân biệt rõ:

- **Command**: yêu cầu một service thực hiện hành động, ví dụ ReserveStock.
- **Event**: thông báo một việc đã xảy ra, ví dụ OrderPlaced.

Command thường có một bên chịu trách nhiệm xử lý. Một event có thể có nhiều subscriber độc lập. Tên event nên mô tả sự việc đã xảy ra và thường dùng thì quá khứ; không dùng event để che giấu một lời gọi command mà người gửi cần kết quả tức thời.

### Bước 7: Thiết kế lỗi và trạng thái trước khi triển khai

Với từng function, ghi rõ điều gì xảy ra khi timeout, xử lý trùng, nhận dữ liệu sai, phụ thuộc bị lỗi hoặc hết số lần retry. Với quy trình nhiều service, xác định trạng thái trung gian, điều kiện hoàn tất và hành động bù trừ.

Một thiết kế chỉ mô tả đường đi thành công chưa đủ để triển khai production. Trong serverless, message có thể được giao lại, event có thể đến chậm và các function có thể chạy đồng thời.

## 4. Ví dụ: phân rã quy trình đặt hàng

Giả sử một ứng dụng bán hàng cần tiếp nhận đơn, giữ hàng, thanh toán và gửi thông báo. Có thể phân chia thành bốn service:

~~~mermaid
flowchart TD
    U[Người mua] --> H[HTTP Function<br/>Order Service]
    H --> O[(Order Data)]
    H -->|OrderPlaced| Q[Event Bus]
    Q --> I[Inventory Function]
    I --> ID[(Inventory Data)]
    I -->|StockReserved / StockRejected| Q
    Q --> P[Payment Function]
    P --> PD[(Payment Data)]
    P -->|PaymentSucceeded / PaymentFailed| Q
    Q --> R[Order Result Function]
    R --> O
    Q --> N[Notification Function]
    N --> E[Email / SMS Provider]
~~~

Các ranh giới có ý nghĩa như sau:

- **Order Service** sở hữu đơn hàng và trạng thái như PENDING, CONFIRMED, REJECTED hoặc CANCELLED.
- **Inventory Service** sở hữu số lượng tồn và các lượt giữ hàng.
- **Payment Service** sở hữu giao dịch, kết quả thanh toán và thông tin đối soát.
- **Notification Service** sở hữu trạng thái gửi thông báo và tích hợp với nhà cung cấp email hoặc SMS.

Một luồng có thể diễn ra như sau:

1. HTTP Function nhận yêu cầu đặt hàng, xác thực đầu vào và gọi ca sử dụng tạo đơn. Order Service ghi đơn ở trạng thái PENDING.
2. Sau khi lưu đơn thành công, Order Service phát event OrderPlaced.
3. Inventory Function nhận event, kiểm tra và giữ hàng. Nó phát StockReserved hoặc StockRejected.
4. Khi hàng đã được giữ, Payment Function xử lý thanh toán và phát PaymentSucceeded hoặc PaymentFailed.
5. Order Result Function nhận kết quả, cập nhật trạng thái đơn. Nếu thanh toán thành công, đơn chuyển sang CONFIRMED; nếu thất bại, đơn có thể chuyển sang trạng thái cần hủy hoặc xử lý tiếp.
6. Notification Function nhận event phù hợp và gửi thông báo. Việc gửi email lỗi không nên làm mất kết quả thanh toán hoặc đảo ngược trạng thái đơn.

Sơ đồ là một ví dụ về phối hợp theo event. Trình tự thực tế cần được định nghĩa rõ: ví dụ Payment chỉ được chạy sau StockReserved, còn khi StockRejected thì không được yêu cầu thanh toán. Nếu quy trình có nhiều nhánh, timeout và hành động bù trừ, có thể dùng một Saga Orchestrator để quản lý trạng thái quy trình. Nếu các bước tương đối độc lập và event thể hiện rõ kết quả, choreography có thể đơn giản hơn.

### 4.1. Chọn orchestration hay choreography

| Cách phối hợp | Đặc điểm | Phù hợp khi |
|---|---|---|
| Orchestration | Một bộ điều phối biết bước tiếp theo, theo dõi trạng thái và quyết định hành động | Quy trình dài, nhiều nhánh, timeout và bước bù trừ phức tạp |
| Choreography | Các service phản ứng với event do service khác phát ra | Các bước ít phụ thuộc, hợp đồng event rõ, nhiều subscriber độc lập |

Choreography giảm sự phụ thuộc vào một bộ điều phối trung tâm, nhưng khi có quá nhiều event và subscriber, luồng tổng thể khó quan sát. Orchestration làm rõ tiến trình nhưng bộ điều phối có thể trở thành nơi tập trung logic. Chọn theo độ phức tạp của quy trình, không theo xu hướng công nghệ.

### 4.2. Vì sao không gom mọi bước vào một function?

Một function lớn thực hiện đặt đơn, giữ hàng, thanh toán và gửi email có vẻ đơn giản lúc đầu. Nhưng khi function timeout sau khi thanh toán thành công, hệ thống cần biết bước nào đã hoàn tất để retry an toàn. Function cũng phải có quyền truy cập vào dữ liệu và dịch vụ của nhiều miền nghiệp vụ, đồng thời mở rộng theo tải của toàn bộ quy trình.

Tách theo service cho phép Inventory mở rộng theo lưu lượng giữ hàng, Payment theo lưu lượng giao dịch và Notification theo số lượng thông báo. Mỗi service chỉ cần quyền phù hợp với dữ liệu của mình. Đổi lại, nhóm phát triển phải xử lý trạng thái phân tán, hợp đồng event và tính nhất quán cuối cùng.

### 4.3. Vì sao không tạo function cho mọi thao tác nhỏ?

Nếu mỗi thao tác nội bộ như tính thuế, chuẩn hóa địa chỉ hoặc kiểm tra một trường đều là function riêng, một yêu cầu đơn giản có thể phải đi qua nhiều lần gọi mạng. Điều này làm tăng độ trễ, số lần tính phí, số điểm lỗi và công sức theo dõi.

Các bước thuần tính toán, có cùng vòng đời và không cần mở rộng hoặc cấp quyền độc lập thường nên là phương thức hoặc thành phần trong cùng function/service. Chỉ tách thành function khi có một lý do vận hành hoặc kiến trúc cụ thể.

## 5. Ánh xạ trigger vào function

Trigger quyết định cách function nhận đầu vào, cách phản hồi và cách xử lý lỗi. Bảng sau giúp chọn loại trigger phù hợp:

| Trigger | Khi nên dùng | Điều cần thiết kế |
|---|---|---|
| HTTP | Người dùng hoặc hệ thống khác cần gọi API và thường cần phản hồi ngay | Xác thực, kiểm tra đầu vào, timeout, mã HTTP, giới hạn tốc độ |
| Queue / message | Công việc có thể xử lý nền, cần đệm tải hoặc retry | Acknowledgement, visibility timeout, retry, dead-letter queue, idempotency |
| Event bus | Một sự kiện nghiệp vụ có thể được nhiều service quan tâm | Schema/version, lọc subscriber, event ID, thứ tự và khả năng phát lặp |
| Scheduler | Công việc định kỳ như đối soát hoặc tổng hợp | Múi giờ, chạy trùng, khóa công việc, cửa sổ xử lý |
| Storage event | Phản ứng khi file hoặc object được tạo/cập nhật | Kích thước file, định danh object, sự kiện lặp và thứ tự |

Không nên chọn trigger chỉ vì nền tảng hỗ trợ nó. Hãy bắt đầu từ nhu cầu của nghiệp vụ: ai khởi tạo, có cần kết quả tức thời không, công việc có thể chờ không và khi lỗi thì ai chịu trách nhiệm thử lại.

## 6. Cấu trúc Java function theo ca sử dụng

Phần xử lý nghiệp vụ nên được giữ trong ca sử dụng hoặc domain service. Function đóng vai trò adapter: chuyển dữ liệu từ trigger thành lệnh nội bộ, gọi nghiệp vụ và chuyển kết quả thành phản hồi phù hợp.

Ví dụ minh họa dưới đây dùng các kiểu HTTP tự định nghĩa để tập trung vào ranh giới kiến trúc; adapter thực tế sẽ được ánh xạ sang kiểu request/response của nền tảng FaaS đang sử dụng.

~~~java
public record PlaceOrderCommand(
        String customerId,
        List<OrderLine> lines,
        String idempotencyKey) {
}

public record OrderLine(String productId, int quantity) {
}

public record PlaceOrderResult(String orderId, String status) {
}

public interface PlaceOrderUseCase {
    PlaceOrderResult execute(PlaceOrderCommand command);
}

public record HttpRequest(
        String customerId,
        List<OrderLine> lines,
        String idempotencyKey) {
}

public record HttpResponse(int statusCode, String body) {
}

public final class PlaceOrderHttpFunction {
    private final PlaceOrderUseCase placeOrder;

    public PlaceOrderHttpFunction(PlaceOrderUseCase placeOrder) {
        this.placeOrder = placeOrder;
    }

    public HttpResponse handle(HttpRequest request) {
        if (request.customerId() == null || request.customerId().isBlank()) {
            return new HttpResponse(400, "customerId is required");
        }

        if (request.lines() == null || request.lines().isEmpty()) {
            return new HttpResponse(400, "order lines are required");
        }

        PlaceOrderCommand command = new PlaceOrderCommand(
                request.customerId(),
                request.lines(),
                request.idempotencyKey());

        PlaceOrderResult result = placeOrder.execute(command);

        return new HttpResponse(
                202,
                "{\"orderId\":\"" + result.orderId()
                        + "\",\"status\":\"" + result.status() + "\"}");
    }
}
~~~

Ví dụ cho thấy function chỉ xử lý giao thức HTTP và chuyển yêu cầu vào ca sử dụng. Quy tắc như giá, giới hạn số lượng, trạng thái đơn và ghi dữ liệu phải nằm trong lớp nghiệp vụ. Trong ứng dụng thực tế, cần dùng JSON serializer thay vì nối chuỗi JSON thủ công, đồng thời xác thực danh tính người gọi và kiểm tra quyền truy cập trước khi thực thi ca sử dụng.

Một function nhận message có cấu trúc tương tự:

~~~java
public record OrderPlacedEvent(
        String eventId,
        String orderId,
        List<OrderLine> lines) {
}

public interface ReserveInventoryUseCase {
    void reserve(OrderPlacedEvent event);
}

public final class ReserveInventoryMessageFunction {
    private final ReserveInventoryUseCase reserveInventory;

    public ReserveInventoryMessageFunction(
            ReserveInventoryUseCase reserveInventory) {
        this.reserveInventory = reserveInventory;
    }

    public void handle(OrderPlacedEvent event) {
        reserveInventory.reserve(event);
    }
}
~~~

Adapter message không cần biết cách Inventory tính số lượng khả dụng. Use case chịu trách nhiệm kiểm tra event đã xử lý chưa, áp dụng quy tắc giữ hàng, lưu kết quả và bảo đảm xử lý lặp an toàn. Adapter của nền tảng chỉ xác nhận message sau khi nghiệp vụ đã được xử lý và dữ liệu đã commit theo đúng cơ chế của nền tảng.

## 7. Thiết kế trạng thái, retry và idempotency

Trong môi trường serverless, retry là một phần bình thường của vận hành. Nền tảng có thể giao lại message khi function timeout hoặc không xác nhận thành công. Một event cũng có thể được phát lại do publisher retry. Vì thế, không nên giả định mỗi function chỉ chạy đúng một lần cho mỗi nghiệp vụ.

### 7.1. Idempotency

Một thao tác idempotent có thể được thực hiện nhiều lần với cùng một định danh mà không làm phát sinh thêm hiệu ứng nghiệp vụ. Ví dụ, nhận lại event OrderPlaced không được tạo thêm một lượt giữ hàng.

Các cách triển khai phổ biến:

- Mỗi yêu cầu hoặc event có một idempotency key ổn định.
- Lưu key đã xử lý cùng kết quả trong cơ sở dữ liệu.
- Đặt unique constraint trên key để ngăn hai instance xử lý đồng thời cùng một yêu cầu.
- Ghi trạng thái xử lý trong cùng transaction với thay đổi nghiệp vụ khi có thể.
- Nếu thao tác gọi hệ thống ngoài, truyền key idempotency sang nhà cung cấp nếu API của họ hỗ trợ.

Không nên chỉ kiểm tra key trong bộ nhớ function vì hai instance có thể chạy song song hoặc một instance mới có thể được tạo sau đó.

### 7.2. Retry và dead-letter queue

Retry phù hợp với lỗi tạm thời như timeout mạng, giới hạn tốc độ hoặc dịch vụ phụ thuộc tạm thời không khả dụng. Nên có giới hạn số lần thử, khoảng chờ tăng dần và jitter để tránh nhiều function cùng retry tại một thời điểm.

Không nên retry vô hạn lỗi dữ liệu không hợp lệ hoặc lỗi nghiệp vụ không thể tự khắc phục. Sau số lần thử cho phép, message có thể được chuyển vào dead-letter queue để kiểm tra và xử lý lại có kiểm soát.

Cần phân biệt:

- **Lỗi tạm thời**: có thể thử lại sau.
- **Lỗi vĩnh viễn**: cần sửa dữ liệu hoặc quy tắc trước khi xử lý lại.
- **Kết quả chưa rõ**: function timeout sau khi gửi yêu cầu đến hệ thống ngoài; cần tra cứu theo transaction ID hoặc idempotency key trước khi thực hiện lại.

### 7.3. Trạng thái quy trình phân tán

Khi một quy trình đi qua nhiều service, không có một transaction cơ sở dữ liệu duy nhất bao phủ tất cả bước. Hãy mô hình hóa trạng thái rõ ràng, ví dụ:

**PENDING → STOCK_RESERVED → PAYMENT_PENDING → CONFIRMED**

Các nhánh lỗi có thể là:

**STOCK_REJECTED**, **PAYMENT_FAILED**, **CANCEL_PENDING**, **CANCELLED**, **REFUND_PENDING**.

Tên trạng thái cần phản ánh sự thật đã được xác nhận. Ví dụ, sau khi gửi yêu cầu thanh toán nhưng chưa nhận kết quả, không nên ghi trạng thái PAID. Có thể dùng PAYMENT_PENDING để thể hiện công việc còn đang diễn ra.

### 7.4. Transactional outbox

Một lỗi phổ biến xảy ra khi service ghi dữ liệu thành công nhưng phát event thất bại, hoặc phát event thành công nhưng transaction ghi dữ liệu bị rollback. Hai thao tác này không tự động nguyên tử với nhau.

Transactional outbox giải quyết vấn đề bằng cách ghi thay đổi nghiệp vụ và bản ghi event vào cùng một transaction:

~~~sql
BEGIN;

INSERT INTO orders (order_id, status)
VALUES ('ORD-1001', 'PENDING');

INSERT INTO outbox (event_id, event_type, payload)
VALUES ('EVT-9001', 'OrderPlaced', '{...}');

COMMIT;
~~~

Một publisher riêng đọc outbox và gửi event đến message broker. Publisher có thể gửi lặp nếu gặp lỗi sau khi broker đã nhận event nhưng trước khi publisher đánh dấu hoàn tất. Vì vậy consumer vẫn phải idempotent. Outbox bảo đảm thay đổi dữ liệu và ý định phát event được lưu cùng nhau; nó không tự biến toàn bộ quy trình phân tán thành exactly-once.

## 8. Quyền truy cập và bảo mật theo ranh giới

Mỗi function nên có danh tính thực thi và quyền tối thiểu cần thiết. Ví dụ:

- PlaceOrderFunction có quyền ghi dữ liệu đơn hàng và phát event OrderPlaced.
- ReserveInventoryFunction có quyền đọc/ghi dữ liệu tồn kho và phát kết quả giữ hàng.
- PaymentFunction có quyền truy cập thông tin xác thực của nhà cung cấp thanh toán và dữ liệu giao dịch.
- NotificationFunction có quyền đọc cấu hình gửi thông báo và gọi nhà cung cấp email/SMS.

Tránh cấp quyền truy cập toàn bộ cơ sở dữ liệu cho mọi function trong cùng một dự án. Quyền nên phản ánh đúng trách nhiệm của function, giúp giảm phạm vi ảnh hưởng khi thông tin xác thực bị lộ hoặc function bị khai thác.

Các bí mật như API key và thông tin kết nối cần được lấy từ secret manager hoặc cơ chế quản lý cấu hình an toàn của nền tảng. Không ghi bí mật vào mã nguồn, biến môi trường được chia sẻ rộng rãi hoặc log.

Với HTTP trigger, cần xác thực người gọi, kiểm tra quyền trên tài nguyên cụ thể và giới hạn tốc độ khi phù hợp. Với message/event trigger, cần kiểm soát quyền publish/subscribe và xác thực nguồn phát. Không mặc định rằng event đến từ broker thì nội dung đã hợp lệ.

## 9. Độ trễ, cold start, mở rộng và chi phí

Phân rã ảnh hưởng trực tiếp đến vận hành. Mỗi function có thể được mở rộng theo lưu lượng riêng, nhưng mỗi lần gọi qua ranh giới function/service có thể tạo thêm độ trễ và chi phí.

### 9.1. Cold start

Cold start xảy ra khi nền tảng cần khởi tạo môi trường thực thi mới trước khi xử lý request. Với Java, thời gian khởi động có thể chịu ảnh hưởng bởi:

- Số lượng thư viện và kích thước artifact.
- Thời gian khởi tạo framework, dependency injection và client.
- Việc nạp cấu hình hoặc thiết lập kết nối trong quá trình khởi tạo.
- Cách đóng gói, runtime và cấu hình tài nguyên của nền tảng.

Có thể giảm tác động bằng cách giữ function tập trung, hạn chế dependency không cần thiết, tránh làm công việc nặng trong static initializer và tái sử dụng client an toàn giữa các lần gọi. Với workload có yêu cầu độ trễ nghiêm ngặt, cần đo cold start thực tế và cân nhắc cơ chế giữ instance sẵn sàng nếu nền tảng hỗ trợ.

Không nên tách một nghiệp vụ thành nhiều function nhỏ chỉ để “nhẹ” hơn mà không đo tổng độ trễ của chuỗi gọi. Nhiều lần khởi tạo và truyền dữ liệu có thể làm kết quả tệ hơn.

### 9.2. Khả năng mở rộng

Function thường mở rộng theo số request hoặc message đang chờ. Điều này hữu ích khi các năng lực có tải khác nhau: Notification có thể tăng đột biến trong khi truy vấn đơn hàng vẫn ổn định.

Tuy nhiên, mở rộng nhanh có thể gây áp lực lên cơ sở dữ liệu, API bên ngoài hoặc giới hạn concurrency. Cần cấu hình giới hạn concurrency, kiểm soát tốc độ tiêu thụ queue và thiết kế backpressure khi phụ thuộc phía sau không thể xử lý cùng tốc độ.

### 9.3. Chi phí

Chi phí serverless thường phụ thuộc vào số lần gọi, thời gian thực thi, cấu hình tài nguyên, lưu trữ, truyền dữ liệu và các dịch vụ phụ trợ. Việc chia nhỏ có thể giúp chỉ mở rộng phần đang có tải, nhưng cũng làm tăng số lần gọi, số message, log, trace và tài nguyên quản lý.

Khi so sánh hai phương án, cần tính cả chi phí gián tiếp:

- Số lần gọi giữa các function và service.
- Thời gian chờ do gọi đồng bộ.
- Số lần retry và message bị xử lý lặp.
- Chi phí lưu trữ trạng thái, outbox, queue và log.
- Công sức phát triển, theo dõi và xử lý sự cố.

Nên đo trên workload đại diện thay vì dựa vào số function hoặc giá niêm yết của một lần gọi đơn lẻ.

## 10. Dấu hiệu nên tách hoặc gộp ranh giới

| Dấu hiệu | Hướng xử lý nên cân nhắc |
|---|---|
| Có ngôn ngữ nghiệp vụ, quy tắc và dữ liệu riêng | Tách thành service có quyền sở hữu rõ |
| Cần mở rộng theo tải khác biệt đáng kể | Tách function hoặc service để scale độc lập |
| Có yêu cầu bảo mật hoặc quyền truy cập khác nhau | Tách function và cấp quyền riêng |
| Có lịch triển khai hoặc nhóm sở hữu độc lập | Ranh giới service riêng có thể hữu ích |
| Hai phần luôn phải cập nhật cùng nhau | Xem lại việc tách quá nhỏ |
| Nhiều lời gọi đồng bộ qua lại trong một thao tác | Xem lại ranh giới hoặc chuyển một phần sang bất đồng bộ |
| Hai thao tác luôn cần cùng transaction để bảo vệ invariant | Giữ trong cùng service/transaction nếu có thể |
| Function chỉ là một phép biến đổi nhỏ, không có yêu cầu vận hành riêng | Giữ thành phương thức hoặc thành phần nội bộ |

Không có quy tắc “mỗi service chỉ có một function” hay “mỗi function phải có một database”. Mức phân rã phù hợp phụ thuộc vào độ phức tạp nghiệp vụ, tải, yêu cầu bảo mật, khả năng vận hành và năng lực của nhóm phát triển.

Với hệ thống còn nhỏ, có thể bắt đầu bằng một ứng dụng được chia module theo bounded context, sau đó triển khai một số entry point dưới dạng function. Khi có bằng chứng về nhu cầu mở rộng, triển khai độc lập hoặc cô lập lỗi, mới tách service. Cách này giúp giữ ranh giới nghiệp vụ rõ ngay từ đầu mà không tạo ra quá nhiều thành phần phân tán quá sớm.

## 11. Những lỗi thiết kế thường gặp

**Chia theo endpoint:** Mỗi endpoint thành một service riêng khiến các quy tắc cùng miền bị phân tán và các thay đổi đơn giản cần phối hợp nhiều nơi. Hãy nhóm endpoint theo năng lực và quyền sở hữu dữ liệu.

**Chia theo bảng:** Một service cho mỗi bảng thường biến quan hệ dữ liệu thành mạng lưới lời gọi. Hãy nhóm dữ liệu theo hành vi nghiệp vụ và invariant cần bảo vệ.

**Dùng chung cơ sở dữ liệu như hợp đồng:** Khi service khác đọc/ghi trực tiếp bảng nội bộ, thay đổi schema có thể phá vỡ nhiều consumer. Hãy dùng API hoặc event được quản lý phiên bản.

**Dùng event cho mọi thứ:** Event không phù hợp khi bên gọi cần câu trả lời tức thì hoặc cần bảo đảm một hành động đã được chấp nhận. Chọn command, API hay event theo ngữ nghĩa và yêu cầu phản hồi.

**Giả định message chỉ đến một lần:** Retry và giao lặp có thể tạo đơn, giữ hàng hoặc thanh toán trùng. Dùng idempotency key, ràng buộc duy nhất và trạng thái xử lý bền vững.

**Để function giữ trạng thái nghiệp vụ trong bộ nhớ:** Instance có thể bị thay thế hoặc chạy song song. Lưu trạng thái cần thiết trong kho dữ liệu phù hợp.

**Bỏ qua quyền truy cập:** Một function có quyền quá rộng làm tăng phạm vi ảnh hưởng của lỗi. Cấp quyền theo đúng dữ liệu và hành động mà function cần.

**Tách quá nhỏ để tối ưu cold start:** Số lần gọi và điểm lỗi tăng có thể làm hệ thống chậm hơn. Đo thời gian khởi động và độ trễ đầu cuối trước khi quyết định.

**Không theo dõi được luồng xuyên service:** Log riêng lẻ không đủ để tìm nguyên nhân một đơn bị treo. Truyền correlation ID, event ID và trace context qua các lời gọi và message; ghi log có cấu trúc nhưng không đưa dữ liệu nhạy cảm vào log.

## 12. Checklist trước khi triển khai

Với mỗi service và function, hãy trả lời được các câu hỏi sau:

- [ ] Trách nhiệm nghiệp vụ của service có thể diễn đạt bằng một câu rõ ràng không?
- [ ] Service sở hữu dữ liệu và các invariant nào?
- [ ] Function được gọi bởi HTTP, message, event hay scheduler? Trigger có đúng với nhu cầu nghiệp vụ không?
- [ ] Đầu vào, đầu ra và hợp đồng lỗi đã được xác định chưa?
- [ ] Trạng thái cần tồn tại qua nhiều lần gọi được lưu ở đâu?
- [ ] Retry có thể xảy ra ở đâu và thao tác đã idempotent chưa?
- [ ] Có cần dead-letter queue, outbox hoặc Saga không?
- [ ] Function có đúng quyền tối thiểu để truy cập dữ liệu và dịch vụ phụ thuộc không?
- [ ] Timeout, concurrency, cold start và giới hạn của dịch vụ phụ thuộc đã được xem xét chưa?
- [ ] Có correlation ID, event ID, log và metric để theo dõi luồng đầu cuối không?
- [ ] Chi phí của số lần gọi, message, lưu trữ và truyền dữ liệu đã được ước lượng trên workload đại diện chưa?
- [ ] Ranh giới này có cho phép thay đổi độc lập mà không tạo ra quá nhiều lời gọi đồng bộ không?

Nếu chưa trả lời được quyền sở hữu dữ liệu, quy tắc nghiệp vụ và cách xử lý khi message được giao lặp, ranh giới chưa đủ rõ để triển khai an toàn.

## Kết luận

Phân rã serverless nên bắt đầu từ năng lực nghiệp vụ và quyền sở hữu dữ liệu. Service tạo ranh giới cho quy tắc, trạng thái và hợp đồng; function là đơn vị thực thi được kích hoạt bởi HTTP, message hoặc event. Sau khi xác định ranh giới, hãy chọn cách giao tiếp, thiết kế trạng thái và lỗi, rồi đánh giá tác động đến quyền truy cập, retry, idempotency, cold start, mở rộng và chi phí. Một thiết kế tốt cho phép từng phần thay đổi và mở rộng có kiểm soát, đồng thời giữ cho toàn bộ quy trình nghiệp vụ có thể hiểu và theo dõi được.

