# Tiêu chí về gắn kết bên trong và liên kết bên ngoài khi xác định ranh giới Microservices

> **Chủ đề:** Software Design Architecture → System Architecture → Microservices → Ranh giới dịch vụ.
>
> **Mục tiêu học tập:** nhận diện tính gắn kết bên trong (cohesion) và mức liên kết bên ngoài (coupling); dùng các tiêu chí nghiệp vụ, dữ liệu, giao tiếp, thay đổi và vận hành để lựa chọn ranh giới service; giải thích khi nào nên gộp, khi nào nên tách; kiểm chứng lựa chọn bằng một luồng nghiệp vụ thực tế.

## 1. Vì sao phải đánh giá cohesion và coupling?

Một hệ thống có thể được chia thành nhiều service theo tên bảng dữ liệu, tầng kỹ thuật, nhóm phát triển hoặc danh sách endpoint. Chia như vậy thường rất nhanh ở giai đoạn vẽ sơ đồ, nhưng có thể dẫn đến hàng loạt request đi qua nhiều service, mỗi thay đổi phải cập nhật nhiều kho mã và việc triển khai cần đồng bộ. Khi đó ta có nhiều tiến trình chạy riêng nhưng **chưa đạt độc lập thay đổi**.

Hai tiêu chí nền tảng để thiết kế ranh giới là:

- **Cohesion — gắn kết bên trong:** các chức năng, dữ liệu, quy tắc và trách nhiệm bên trong một service liên quan chặt chẽ với **một năng lực nghiệp vụ rõ ràng** tới đâu.
- **Coupling — liên kết bên ngoài:** service phụ thuộc vào service khác tới mức nào để **thực thi, thay đổi, kiểm thử, phát hành và phục hồi**.

Mục tiêu thông thường là **cohesion cao, coupling được kiểm soát và đủ thấp**. Nhưng đó không phải một công thức máy móc: hai thao tác vốn phải đảm bảo một bất biến giao dịch chung có thể cần ở cùng một ranh giới, dù sơ đồ nghiệp vụ cho thấy hai khái niệm khác nhau. Ngược lại, hai chức năng dùng cùng một framework không vì vậy mà thuộc cùng service.

### 1.1. Mục tiêu thực tế của ranh giới tốt

Một service có ranh giới hợp lý thường có thể:

1. Giải thích trách nhiệm chính của mình bằng một câu nghiệp vụ, chẳng hạn “quản lý vòng đời reservation của hàng tồn”.
2. Sở hữu các quy tắc và dữ liệu cần để đưa ra quyết định trong phạm vi đó.
3. Thay đổi một quy tắc thông thường mà không bắt buộc nhiều service khác phải sửa và triển khai đồng loạt.
4. Đưa ra contract rõ ràng cho bên ngoài và bảo vệ invariant nội bộ.
5. Hoạt động, kiểm thử và xử lý lỗi trong phạm vi trách nhiệm đã công bố.
6. Có owner cụ thể chịu trách nhiệm chất lượng, bảo mật, latency và sự cố.

Điều này **không đòi mỗi service phải hoàn toàn độc lập với tất cả service khác**. Các luồng thanh toán, đặt hàng và giao nhận buộc phải phối hợp. Chất lượng ranh giới thể hiện ở chỗ sự phối hợp đó **có chủ đích, có hợp đồng ổn định và không lan trách nhiệm tùy tiện**.

## 2. Cohesion: thế nào là gắn kết bên trong tốt?

Cohesion cao không đơn giản là “các lớp gọi nhau nhiều” hoặc “các lớp đều làm việc với một database”. Đó là mức các thành phần cùng hướng tới một mục đích nghiệp vụ và thường cần thay đổi cùng nhau để giữ đúng các quy tắc của mục đích đó.

### 2.1. Gắn kết theo năng lực nghiệp vụ

Câu hỏi đầu tiên: **service tạo ra kết quả nghiệp vụ nào?** 

Ví dụ với hệ thống thương mại điện tử:

- **Catalog** quản lý thông tin hiển thị của sản phẩm, phân loại, mô tả và thuộc tính được công bố.
- **Inventory** quản lý tồn có thể bán, reservation, xuất/nhập và giải phóng lượng giữ.
- **Order** quản lý trạng thái đơn và lịch sử thay đổi vòng đời đặt hàng.
- **Payment** quản lý yêu cầu thanh toán, giao dịch với nhà cung cấp thanh toán và đối soát.
- **Notification** xử lý chính sách tạo/gửi thông báo qua các kênh.

Các chức năng “tạo reservation”, “giữ hạn mức tồn” và “hủy reservation” có cohesion cao trong Inventory, vì chúng cùng bảo vệ số lượng có thể bán. “Render HTML cho email” dù được kích hoạt sau khi đặt hàng không nhất thiết là trách nhiệm của Order.

**Dấu hiệu yếu:** đặt tất cả controller có tên Customer, Product, Order vào một service vì chúng cùng là REST API; hoặc đặt tất cả tác vụ gửi email, tính giá, cập nhật tồn và ghi thanh toán trong một “Utility Service”.

### 2.2. Gắn kết theo quy tắc và bất biến nghiệp vụ

**Invariant** là điều kiện phải luôn đúng ở điểm hệ thống cam kết một trạng thái; ví dụ:

- Không xác nhận hai reservation chiếm cùng một đơn vị tồn kho nếu tổng quyền giữ không đủ.
- Không áp dụng cùng một yêu cầu hoàn tiền hai lần.
- Không chuyển đơn hàng từ trạng thái CANCELLED về PAID bằng một event đến trễ mà không theo chính sách chuyển trạng thái.
- Không cho phép tài khoản vượt hạn mức đã được giữ trong giao dịch có thẩm quyền.

Nếu nhiều thao tác cần được kiểm tra và commit **nguyên tử** để bảo vệ cùng một invariant, đó là tín hiệu mạnh để chúng ở **cùng transactional boundary** hoặc có một owner chịu quyết định. Phân tách chúng chỉ vì có hai danh từ khác nhau có thể biến một transaction cục bộ thành giao thức phân tán phức tạp.

Ví dụ:

~~~text
Inventory Service
  - reserveStock(sku, quantity, reservationId)
  - confirmReservation(reservationId)
  - releaseReservation(reservationId)
  - getAvailableToPromise(sku)
  - InventoryBalance
  - Reservation
  - Quy tắc: không xác nhận vượt lượng được phép giữ
~~~

Các thành phần này cùng thay đổi khi chính sách giữ hàng, thời hạn reservation hay cách tính tồn thay đổi. Gắn kết theo invariant thường đáng tin hơn việc chia một service cho “bảng inventory” và một service cho “bảng reservation” rồi buộc chúng gọi nhau cho mọi cập nhật.

### 2.3. Gắn kết theo lý do thay đổi

Một tiêu chí hữu ích là **“các chức năng này thường thay đổi cùng nhau vì cùng một nguyên nhân nghiệp vụ không?”**.

Ví dụ:

- Luật tính hạn dùng của reservation thay đổi → các nghiệp vụ reserve, expire và release phải được xem xét chung.
- Nhà cung cấp cổng thanh toán thay đổi → adapter thanh toán, đối soát và xử lý callback của Payment thay đổi; cấu trúc tổng tiền của Order không nhất thiết thay đổi.
- Cách hiển thị hình ảnh Catalog thay đổi → Inventory và Payment không cần deploy.

Nếu hai tập chức năng liên tục thay đổi cùng nhau vì *một chính sách chung*, việc đặt chung ranh giới có thể giảm chi phí phối hợp. Nếu thay đổi của một nhóm thường không liên quan tới nhóm kia nhưng lại buộc kiểm thử, phát hành hoặc sửa code của nhau, có thể đang gộp quá nhiều trách nhiệm.

Cần cẩn trọng: **hai file thường xuất hiện cùng một pull request** không chứng minh chúng thuộc cùng service. Có thể đó là hệ quả của cách chia đội, framework, migration hàng loạt hoặc một thiết kế coupling vốn đã sai. Phải đọc *nguyên nhân thay đổi*, không chỉ đếm file.

### 2.4. Gắn kết của mô hình dữ liệu

Một service nên quản lý mô hình dữ liệu có ngữ nghĩa và vòng đời gắn với trách nhiệm chính. Các trường hợp như reservation và available quantity có thể cần được cập nhật bằng một transaction cục bộ.

Tuy nhiên, việc hai chức năng cùng dùng một database không chứng minh cohesion cao. Cũng không phải mỗi bảng là một bounded context. Phân ranh giới theo bảng dẫn tới các dịch vụ CRUD quá nhỏ: service A chỉ giữ Order, service B chỉ giữ OrderLine, service C chỉ giữ OrderStatus. Mọi thao tác tạo đơn phải phối hợp ba nơi, làm tăng coupling và chi phí lỗi mạng.

**Data ownership** cần trả lời:

- Dịch vụ nào được phép tạo, sửa, xóa dữ liệu có thẩm quyền?
- Dịch vụ nào định nghĩa ý nghĩa và invariant của dữ liệu đó?
- Dịch vụ khác đọc dữ liệu bằng contract nào?
- Nếu một service ngừng hoạt động, ai vẫn được phép ra quyết định dựa trên bản dữ liệu đã sao chép?

Cùng dùng một cụm database về mặt hạ tầng không nhất thiết sai, nhưng các service không nên tùy tiện truy cập và sửa trực tiếp bảng riêng của nhau; nếu không, tính tự chủ chỉ tồn tại trên sơ đồ triển khai.

### 2.5. Gắn kết theo vòng đời và quyền sở hữu

Hai chức năng có cùng ownership, quy trình release, bảo mật và yêu cầu vận hành có thể hưởng lợi khi ở chung service. Một nhóm sở hữu toàn bộ reservation workflow thường xử lý sự cố thuận lợi hơn mô hình phân tán trách nhiệm giữa nhiều nhóm mà không có giao thức phối hợp rõ.

Dù vậy, “cùng một team” **không phải căn cứ duy nhất** để gộp. Cấu trúc đội nhóm có thể thay đổi; service nên có ranh giới nghiệp vụ đủ bền để không phải chia lại mỗi lần sơ đồ tổ chức thay đổi.

## 3. Coupling: thế nào là phụ thuộc bên ngoài?

Một dependency đơn lẻ chưa phải vấn đề. Mục tiêu là đánh giá **mức độ thay đổi hoặc sự cố của một service có thể buộc service khác thay đổi hoặc ngừng phục vụ**.

Có nhiều dạng coupling khác nhau. Một hệ thống có thể ít phụ thuộc ở mức code nhưng vẫn phụ thuộc rất chặt ở mức dữ liệu và vận hành.

### 3.1. Coupling về hợp đồng và cấu trúc mã

Service A phụ thuộc trực tiếp vào chi tiết nội bộ của Service B khi:

- A import entity/domain model nội bộ của B, rồi tự suy ra các quy tắc của B.
- A phải sửa khi B đổi tên cột database hoặc thêm một thuộc tính không liên quan tới API công bố.
- A phụ thuộc vào lớp nội bộ, shared library mang toàn bộ domain objects của B.
- Mỗi thay đổi API của B đều làm A không build hoặc chạy được.

**Coupling thấp hơn** khi A chỉ hiểu một contract ổn định: một lệnh theo mục đích nghiệp vụ hoặc một sự kiện công khai, có version/schema và hành vi lỗi được xác định.

So sánh:

~~~text
Phụ thuộc vào cấu trúc nội bộ:
Order -> đọc bảng stock_balance, stock_reservation của Inventory
      -> tự tính available = balance - reserved
      -> tự UPDATE reserved

Phụ thuộc vào hành vi được công bố:
Order -> Inventory.reserve(sku, quantity, reservationId)
      <- RESERVED | INSUFFICIENT_STOCK | UNKNOWN/PENDING
~~~

Ở cách thứ hai, Inventory được quyền thay đổi mô hình lưu trữ, thuật toán reservation và chiến lược cache, miễn giữ được ý nghĩa contract.

### 3.2. Coupling về thời gian chạy (temporal coupling)

Hai service bị **temporal coupling** khi một bên bắt buộc bên kia phải hoạt động và phản hồi ngay tại thời điểm xử lý.

Ví dụ một endpoint checkout gọi tuần tự:

~~~text
POST /checkout
   -> Customer Service
   -> Promotion Service
   -> Pricing Service
   -> Inventory Service
   -> Payment Service
   -> Shipping Service
   -> Notification Service
   -> trả kết quả
~~~

Nếu mọi lời gọi là bắt buộc, sự cố hoặc độ trễ của bất kỳ phụ thuộc nào có thể làm cả request thất bại. Số dependency trên critical path càng nhiều, càng khó cam kết latency và availability đầu cuối.

Temporal coupling có thể giảm bằng cách:

- Tránh gọi service từ xa cho những dữ liệu sẵn có và đã được phép sao chép.
- Gộp thao tác nhỏ thành API theo mục đích nghiệp vụ để tránh chatty request.
- Chuyển tác vụ không cần phản hồi ngay sang event/queue: gửi email hoặc cập nhật analytics.
- Dùng cache/read model có chính sách freshness rõ ràng.
- Tách trạng thái **ACCEPTED/PENDING** khỏi **CONFIRMED/SUCCESS**, khi nghiệp vụ cho phép xử lý sau.

**Bất đồng bộ không tự động làm biến mất coupling**: nó chuyển coupling từ “phải hoạt động cùng lúc” sang phụ thuộc vào contract sự kiện, khả năng giao hàng, thứ tự message và eventual consistency.

### 3.3. Coupling về dữ liệu

Dạng coupling thường nguy hiểm nhất là nhiều service cùng phụ thuộc một mô hình dữ liệu chi tiết.

Ví dụ Order truy vấn trực tiếp bảng PaymentTransaction để xem đã thanh toán chưa. Payment đổi schema, định nghĩa “đã settle” hoặc cách lưu nhiều giao dịch thử lại → Order có thể sai dù API Payment không đổi. Nếu Order còn cập nhật bảng của Payment, hai bên không thể thay đổi độc lập và khó phân định trách nhiệm dữ liệu.

Giải pháp:

- Một service là **source of truth** cho từng quyết định.
- Service khác dùng API/query/event đã công bố; chỉ giữ bản sao phục vụ nhu cầu của mình.
- Read model được cập nhật bằng event phải có quy tắc replay, khôi phục, đối chiếu và freshness.
- Không dùng database integration hay shared entity model như API ngầm định.
- Khi cần một transaction mạnh trên cùng invariant, xem xét lại ranh giới thay vì mặc định phải dùng Saga cho mọi thứ.

### 3.4. Coupling về phiên bản và triển khai

Một trong các dấu hiệu microservice không đạt mục tiêu là **coordinated deployment**: mỗi khi đổi Payment, Order, Gateway và Notification đều phải deploy đúng cùng phiên bản trong một cửa sổ ngắn.

Nguyên nhân có thể là API thay đổi không tương thích, shared dependency bị nâng cấp đồng thời, database migration phá vỡ bản cũ, hoặc workflow lẫn lộn ownership.

Cách giảm:

- Thiết kế contract **tương thích lùi** trong thời gian rollout, thêm field tùy chọn trước khi gỡ field cũ.
- Dùng bước **expand → migrate → contract** cho schema và event.
- Chạy consumer-driven contract tests tại ranh giới khi phù hợp.
- Duy trì khả năng chạy song song phiên bản cũ/mới trong rolling hoặc canary deployment.
- Đưa dữ liệu version/semantics vào event, có quy tắc xử lý message không hỗ trợ.
- Tránh shared domain libraries khiến nhiều service phải nâng cấp cùng lúc chỉ vì một model thay đổi.

Không phải “deploy độc lập” nghĩa là mọi phiên bản tùy ý đều tương thích mãi mãi; tổ chức cần một **cửa sổ tương thích được công bố và kiểm thử**.

### 3.5. Coupling về giao dịch và nhất quán

Một workflow có nhiều service nhưng mọi bước phải “cùng thành công hoặc cùng rollback tức thời” có **transactional coupling** rất cao.

Ví dụ tạo đơn, giữ kho, xác nhận thanh toán, tạo vận đơn là các công việc thuộc nhiều owner khác nhau. Nếu cần kết quả nguyên tử trên toàn hệ, sẽ phát sinh distributed transaction hoặc cơ chế phối hợp, compensation và reconciliation phức tạp.

Giảm coupling bằng cách phân biệt:

1. **Invariant cục bộ phải giữ ngay**: xử lý trong cùng owner/transaction khi có thể.
2. **Quy trình liên miền**: mô hình hóa dưới dạng state machine/Saga với các bước và trạng thái có thể quan sát.
3. **Tác dụng phụ có thể trễ**: phát event hoặc queue sau khi commit; consumer xử lý idempotent.
4. **Lỗi không chắc chắn**: có trạng thái UNKNOWN/PENDING và truy vấn/đối soát, không phán đoán từ timeout.
5. **Compensation có ngữ nghĩa nghiệp vụ**: hủy giữ kho hoặc hoàn tiền không tương đương rollback giao dịch cơ sở dữ liệu.

### 3.6. Coupling về sự cố, tài nguyên và vận hành

Hai service có thể có source code độc lập nhưng cùng phụ thuộc một broker, cụm database, network gateway hoặc quota tài nguyên. Một sự cố tài nguyên chung kéo cả hai xuống.

Các hình thức khác gồm:

- A retry vô hạn khi B chậm, gây quá tải thêm cho B.
- A giữ thread/connection trong lúc đợi B, cạn tài nguyên rồi kéo C bị ảnh hưởng theo.
- Một schema/event sai ở B làm consumer A liên tục crash hoặc kẹt queue.
- Hai service dùng chung credentials với quyền rộng và chung lịch rotation secrets.
- Một deployment thay đổi network policy hoặc shared infrastructure làm nhiều service lỗi cùng lúc.

Cần theo dõi dependency graph, đặt timeout/deadline, giới hạn retry, bulkhead, circuit breaker, backpressure, rate limit và policy graceful degradation. Các cơ chế này **không sửa được ranh giới nghiệp vụ sai**, nhưng giảm mức độ lan truyền sự cố từ những dependency không thể tránh.

### 3.7. Coupling về tổ chức và cách phối hợp

Một thay đổi nhỏ ở Pricing mà phải xin phê duyệt, chỉnh code và deploy qua bốn team cho thấy coupling về tổ chức. Điều này có thể do ranh giới nghiệp vụ không rõ hoặc do một service “chia sẻ” không có owner.

Ngược lại, một team quản lý quá nhiều domain không liên quan có thể trở thành điểm nghẽn dù code ít phụ thuộc. Ranh giới nên hỗ trợ nhóm **sở hữu một luồng giá trị hay năng lực nghiệp vụ**, với quyền thay đổi trong vùng trách nhiệm và hợp đồng phối hợp rõ.

Đó là mối liên hệ với **Conway’s Law**: cấu trúc giao tiếp của tổ chức thường phản ánh vào kiến trúc hệ thống. Đây là tín hiệu cần xem xét, không phải lý do tự động biến sơ đồ nhân sự thành sơ đồ microservices.

## 4. Đọc cohesion và coupling cùng nhau

Hai tiêu chí phải được xem trên cùng một bản thiết kế. Chỉ tối đa hóa cohesion mà bỏ qua external coupling có thể tạo service quá nhỏ; chỉ giảm số lời gọi bằng cách dồn toàn bộ nghiệp vụ vào một service có thể tạo service quá lớn.

| Trường hợp | Cohesion nội bộ | Coupling bên ngoài | Gợi ý đọc dấu hiệu |
| --- | --- | --- | --- |
| Inventory sở hữu reserve, confirm, release và invariant tồn kho | Cao | Hợp đồng nghiệp vụ rõ với Order | Ranh giới có ý nghĩa |
| Một service chỉ xử lý CRUD cho bảng OrderLine | Thấp hoặc quá hẹp | Gọi Order liên tục, dùng chung schema | Nguy cơ “nano service” |
| Service “Common” chứa email, thuế, giá, tồn kho, tài khoản | Thấp | Rất nhiều consumer trực tiếp | Có thể là điểm nghẽn thay đổi |
| Order tự sửa bảng Payment | Có thể trông gọn trong code Order | Data coupling rất cao | Ranh giới owner bị vi phạm |
| Notification tiêu thụ OrderConfirmed event | Cao cho trách nhiệm thông báo | Event contract, queue, delivery semantics | Coupling được điều phối |
| Order, Inventory, Payment phải deploy cùng lúc mỗi tuần | Dù service nhỏ | Version/change coupling rất cao | Dấu hiệu distributed monolith |

Câu hỏi quan trọng là **“phụ thuộc này tồn tại vì một nhu cầu nghiệp vụ thật hay vì cách chia ranh giới hiện tại?”**. Một request cần xác nhận thanh toán từ Payment là dependency nghiệp vụ tự nhiên. Order phải gọi ProductEntityService chỉ để lấy tên sản phẩm rồi mới tạo một dòng đơn hàng có thể là dấu hiệu chia đối tượng quá vụn hoặc thiếu read model.

## 5. Đánh giá bằng dấu hiệu thực tế

Không có một con số duy nhất chứng minh ranh giới tốt. Nên phối hợp **bằng chứng định tính từ domain** và **dữ liệu đo từ hệ thống**.

### 5.1. Dấu hiệu cohesion cao

Hãy kiểm tra mỗi service:

- Có một nhiệm vụ nghiệp vụ chính dễ mô tả hay không?
- Các lệnh cốt lõi cùng bảo vệ một hoặc vài invariant liên quan hay không?
- Các dữ liệu có cùng owner, ngữ nghĩa và vòng đời hay không?
- Khi chính sách nghiệp vụ thay đổi, phần lớn thay đổi có nằm trong service không?
- Service có thể kiểm thử quy tắc chính mà không cần dựng hầu hết các service khác không?
- Các API public có cùng ngôn ngữ miền nghiệp vụ hay chỉ là phép CRUD của các bảng tùy ý?
- Có thể chỉ ra phần nào rõ ràng không thuộc trách nhiệm service không?

Cần tránh dùng “ít class”, “ít dòng code” hoặc “ít bảng” làm thước đo chính. Một service có nhiều class nhưng cùng phục vụ một năng lực có thể cohesion rất cao; một service có hai class nhưng hai trách nhiệm không liên quan vẫn có cohesion thấp.

### 5.2. Dấu hiệu coupling cao

Quan sát trong thay đổi và runtime:

- Một user story đơn giản cần sửa đồng thời nhiều service.
- Thường xuyên phải phát hành nhóm phiên bản cùng lúc.
- Sửa một cột database làm test nhiều service khác thất bại.
- Có các chuỗi HTTP/gRPC đồng bộ dài hoặc vòng gọi A → B → A.
- Mỗi request từ người dùng tạo nhiều remote calls chỉ để tính một quy tắc.
- Service phải biết state machine hoặc loại exception nội bộ của service khác.
- Test component của service A chỉ chạy được khi dựng môi trường gần như production.
- Có nhiều shared libraries chứa domain entities giữa các service.
- Lỗi hoặc quá tải một service không quan trọng làm dừng critical path.
- Các thay đổi cross-team tốn nhiều cuộc họp hơn bản thân phần triển khai.

Một tín hiệu riêng lẻ không đủ để kết luận. Ví dụ Payment có thể bắt buộc đồng bộ trong một loại checkout; vấn đề là **hệ thống có tách được các tác vụ không cần đồng bộ và xử lý khi Payment không phản hồi hay không**.

### 5.3. Ma trận phụ thuộc (dependency matrix)

Có thể lập ma trận các service theo tương tác:

~~~text
                   Catalog   Pricing   Inventory   Payment   Notification
Order                 R          R         W          W           E
Catalog               -          -         -          -           -
Pricing               R          -         -          -           -
Inventory             -          -         -          -           -
Payment               -          -         -          -           E

Ký hiệu:
R = đọc/tra cứu qua contract
W = yêu cầu thao tác nghiệp vụ
E = publish/consume event theo contract
- = không có dependency trực tiếp
~~~

Không phải mọi cạnh trên đồ thị đều “xấu”. Cần bổ sung:

- **Đồng bộ hay bất đồng bộ?** Endpoint có nằm trên critical path không?
- **Chiều sở hữu:** ai sở hữu dữ liệu, ai chỉ tiêu thụ bản sao?
- **Mức cần thiết:** có thể cắt cạnh bằng đổi flow hoặc local read model không?
- **Độ ổn định:** hai bên thường đổi cùng nhau không?
- **Mức lan truyền sự cố:** B chậm có làm A ngừng hay chỉ làm trễ một tác vụ nền?
- **Trạng thái dữ liệu:** có vòng phụ thuộc gây xung đột hay transaction kéo dài không?

Cấu trúc ma trận giúp đội nhìn thấy vòng coupling A ↔ B, các “hub” quá nhiều consumer và điểm nghẽn trong một request dài.

### 5.4. Dữ liệu thay đổi, không chỉ phụ thuộc mã nguồn

Nếu có lịch sử triển khai, lấy mẫu các thay đổi nghiệp vụ gần đây và ghi lại:

| Câu hỏi | Dấu hiệu tốt | Dấu hiệu đáng điều tra |
| --- | --- | --- |
| Một tính năng có thể hoàn thành trong mấy service? | Phần lớn logic trong service owner, các contract ổn định | Nhiều service cùng sửa vì một quy tắc |
| Một migration có cần deploy đồng loạt không? | Expand/contract, bản cũ/mới chạy cùng | Bắt buộc downtime hoặc release cùng lúc |
| Một service lỗi có ảnh hưởng bao nhiêu luồng? | Chỉ các khả năng phụ thuộc thực sự | Lan sang nghiệp vụ không liên quan |
| Có bao nhiêu remote hop trong critical path? | Số hop có lý do nghiệp vụ rõ | Nhiều lời gọi nhỏ, nối tiếp, lặp lại |
| Tính đúng đắn phụ thuộc đâu? | Invariant có owner/transaction boundary | Bất biến trải trên nhiều service mà không có giao thức |
| Test và release có cần dựng toàn hệ thống? | Component/contract test độc lập tương đối | E2E là cách duy nhất biết thay đổi an toàn |

Có thể theo dõi **change coupling ratio**: trong một tập thay đổi nghiệp vụ được phân loại thủ công, bao nhiêu thay đổi bắt buộc chỉnh cả hai service A/B. Đây là chỉ dấu để hỏi “có nên gộp hoặc sửa contract?”, không phải điểm số tuyệt đối: dữ liệu lịch sử bị ảnh hưởng bởi cách tổ chức repo và cách nhóm gộp pull request.

### 5.5. Đo runtime coupling

Từ distributed tracing và metrics, nên xem:

- Số remote calls trên một request quan trọng.
- Độ sâu chuỗi gọi đồng bộ.
- Latency p50/p95/p99 của request đầu cuối và từng dependency.
- Tỷ lệ timeout/retry, số lần circuit breaker mở, queue depth/consumer lag.
- Phần trăm request bị lỗi theo dependency; thời gian phục hồi sau khi một service mất.
- Số sự cố cross-service và thời gian xác định owner.

Ví dụ, nếu checkout p95 = 850 ms, Order xử lý logic chỉ 30 ms nhưng chờ bốn cuộc gọi tuần tự chiếm phần lớn thời gian, đó là dữ liệu để xem lại cách chia API, caching, song song hóa hoặc ranh giới đồng bộ. Không nên cộng trực tiếp p95 của từng hop để khẳng định p95 toàn tuyến; cần đo phân phối thực tế của cả flow.

## 6. Kết hợp với Domain-Driven Design

### 6.1. Business capability và bounded context

Trong Domain-Driven Design (DDD), **bounded context** là ranh giới mà một mô hình và ngôn ngữ nghiệp vụ có ý nghĩa nhất quán. Đây là công cụ rất hữu ích để nghĩ về service boundaries.

Một từ như “Customer” có thể mang nghĩa khác nhau:

- Với CRM: thông tin liên hệ và hoạt động chăm sóc.
- Với Billing: pháp nhân chịu trách nhiệm thanh toán.
- Với Delivery: địa chỉ giao nhận và người nhận thực tế.

Ép ba nhóm dùng một Customer entity khổng lồ có thể gây coupling dù tên đối tượng giống nhau. Tốt hơn là phân định owner và dùng **published language / contract** để ánh xạ các khái niệm liên quan.

**Không có quy tắc bắt buộc 1 bounded context = 1 microservice.** Một bounded context có thể gồm nhiều module được triển khai chung; một service ban đầu có thể chứa nhiều bounded context được tách mã và quyền sở hữu nội bộ rõ ràng. Hãy dựa vào nhu cầu deploy, scale, team và data consistency để quyết định đơn vị vận hành.

### 6.2. Tìm invariant và transaction boundary trước khi tách

Khi vẽ một luồng nghiệp vụ, đánh dấu:

1. Trạng thái nào phải luôn đúng tức thì?
2. Quyết định ghi nào cần atomic commit?
3. Ai là nơi có đủ thông tin và quyền để xác nhận?
4. Bên nào được phép tiêu thụ trạng thái cũ hoặc chờ event?
5. Bước nào là tác dụng phụ có thể retry?
6. Nếu một bước thành công còn bước sau lỗi, quy tắc bù hoặc đối soát là gì?

Từ đó hình thành **aggregate** hoặc transactional unit trong một owner. Các aggregate khác nhau có thể cùng service nếu gắn kết nghiệp vụ cao và cần phối hợp thường xuyên, nhưng không có nghĩa tất cả thay đổi trong service đều phải nằm trong cùng một transaction khổng lồ.

### 6.3. Sơ đồ context mapping

Ví dụ:

~~~text
          +--------------------+
          | Catalog Context    |
          | Mô tả và công bố   |
          +----------+---------+
                     |
            Published Product Snapshot
                     |
                     v
+--------------------+---------------------+
| Order Context                            |
| Order state, order line, customer intent  |
+---------------+--------------------------+
                |
       ReserveStock command
                |
                v
+-------------------------------+
| Inventory Context             |
| Quantity, Reservation, expiry |
+-------------------------------+

Order -> Payment: AuthorizePayment
Payment -> Order: PaymentAuthorized / PaymentFailed
Order -> Notification: OrderConfirmed event
~~~

Order cần một snapshot tên/giá sản phẩm tại lúc tạo đơn nhưng không cần đọc trực tiếp bảng hiện tại của Catalog mọi khi hiển thị đơn cũ. Inventory sở hữu quyền giữ và không để Order tự sửa số tồn.

Mỗi mũi tên là một quan hệ cần mô tả rõ: sync hay async, lỗi, độ trễ chấp nhận, version contract, idempotency và data freshness.

## 7. Ví dụ phân tích ba phương án ranh giới

Giả sử một sản phẩm có các hành động: tạo đơn hàng, giữ tồn kho, tính giá, thu tiền và gửi xác nhận.

### 7.1. Phương án A — chia theo entity CRUD

~~~text
OrderService       -> quản lý bảng orders
OrderLineService   -> quản lý bảng order_lines
StockService       -> quản lý stock
ReservationService -> quản lý reservations
PriceService       -> quản lý bảng prices
PaymentService     -> quản lý giao dịch thanh toán
~~~

Mỗi thao tác thêm một dòng đơn phải gọi nhiều service. Một thay đổi chính sách đặt hàng có thể đòi sửa Order, OrderLine, Stock và Reservation. Bất biến tồn kho bị chia giữa Stock và Reservation; mỗi service hiểu chi tiết dữ liệu của service khác.

**Vấn đề chính:** service quá nhỏ so với invariant và năng lực nghiệp vụ. Dù code mỗi service ngắn, cohesion theo nghiệp vụ không cao và coupling về thời gian chạy, giao dịch, thay đổi đều lớn. Đây là nguy cơ **nano services / distributed monolith**.

### 7.2. Phương án B — chia theo năng lực nghiệp vụ

~~~text
Order
  - createOrder, changeOrderState, order history
  - Order + OrderLine theo aggregate phù hợp

Inventory
  - reserve, confirm, release
  - Stock + Reservation cùng invariant

Pricing
  - tính báo giá, quy tắc khuyến mãi và điều kiện áp dụng

Payment
  - authorize, capture, refund, reconcile

Notification
  - chọn template/kênh, gửi và retry thông báo
~~~

Order gửi lệnh reserve qua contract rõ, Inventory quyết định số lượng có thể giữ. Payment xử lý riêng yêu cầu ủy quyền thanh toán. Notification tiêu thụ sự kiện sau khi Order đã có kết quả đủ chắc chắn.

Ưu điểm: mỗi service có một vai trò giải thích được, dữ liệu và invariant có owner, tốc độ phát hành có thể độc lập hơn. Chi phí còn lại là Saga/state machine, contract tests, tracing và khả năng xử lý partial failure.

### 7.3. Phương án C — giữ module trong modular monolith

~~~text
Application chung
  - order module
  - inventory module
  - pricing module
  - payment integration module
  - notification module
~~~

Các module có API nội bộ rõ, chỉ owner được sửa dữ liệu và có thể dùng cùng deployment. Đây có thể là lựa chọn phù hợp nếu đội nhỏ, hệ thống chưa đòi scale/triển khai riêng hoặc invariants còn thay đổi nhanh.

Phương án này **không đồng nghĩa thiết kế thiếu ranh giới**. Nó vẫn có thể giữ cohesion cao và coupling giữa module thấp; việc triển khai chung làm giảm overhead mạng, bảo mật, tracing và CI/CD. Sau khi có bằng chứng, đội có thể tách module thành service bằng contract đã định nghĩa từ trước.

### 7.4. Chọn phương án bằng tiêu chí nào?

Không có kết luận rằng microservices luôn tốt hơn modular monolith. Nên chọn theo khả năng đạt mục tiêu cụ thể:

| Tiêu chí | Entity CRUD services | Business capability services | Modular monolith có ranh giới |
| --- | --- | --- | --- |
| Cohesion theo nghiệp vụ | Thường thấp/quá vụn | Có thể cao nếu phân miền đúng | Có thể cao ở mức module |
| Giao dịch cục bộ | Bị chia nhỏ | Trong từng owner, liên miền phối hợp rõ | Thường dễ xử lý nếu chung database |
| Network coupling | Rất nhiều hop | Những hop có ý nghĩa nghiệp vụ | Ít hoặc không có hop nội bộ |
| Deploy độc lập | Nhiều deployment nhưng thường phụ thuộc | Có giá trị khi contract ổn định | Deploy chung toàn ứng dụng |
| Chi phí vận hành | Cao so với giá trị mang lại | Có thể đáng trả nếu scale/team cần | Thường thấp hơn khi quy mô nhỏ |
| Dễ tách thêm về sau | Khó nếu coupling dữ liệu lớn | Ranh giới đã thiết kế để độc lập | Cần kỷ luật module và data ownership |

## 8. Thiết kế contract để giảm coupling mà không làm loãng cohesion

### 8.1. API theo ý định nghiệp vụ

Thay vì cho bên ngoài đọc/ghi mô hình lưu trữ:

~~~text
POST /inventory-table/{sku}/increment-reserved
PATCH /reservation-row/{id}
GET  /warehouse-table/{id}
~~~

Có thể công bố lệnh có ý nghĩa:

~~~http
POST /inventory/reservations
Idempotency-Key: order-845-reserve-v1
Content-Type: application/json

{
  "orderId": "845",
  "sku": "BOOK-01",
  "quantity": 1
}
~~~

Phản hồi có thể mô tả kết quả:

~~~json
{
  "reservationId": "res-723",
  "state": "RESERVED",
  "expiresAt": "2027-01-11T10:00:00Z"
}
~~~

Các mã trạng thái cần công bố, chẳng hạn RESERVED, OUT_OF_STOCK, PENDING hoặc UNKNOWN, cùng quy tắc khi timeout. Client không tự cập nhật “reservedQuantity” trong database Inventory.

Một contract tốt cho phép service thay đổi cách cài đặt bên trong mà consumer vẫn dùng đúng thao tác.

### 8.2. Giảm coupling bằng event

Ví dụ Notification không cần Order gọi đồng bộ “gửi email và chờ kết quả” trong critical path. Order có thể phát sự kiện **OrderConfirmed** sau khi commit trạng thái đơn.

~~~text
Order Service
  -> ghi CONFIRMED và outbox event trong cùng transaction cục bộ
  -> dispatcher gửi OrderConfirmed
  -> Notification Consumer
       -> chọn template
       -> gửi email
       -> ghi nhận event đã xử lý
~~~

Ở đây Order chỉ cần biết ngữ nghĩa sự kiện đã xác nhận, không cần biết email provider, template hay lịch retry. Notification chịu trách nhiệm những chi tiết đó.

Nhưng event cũng tạo hợp đồng: tên sự kiện, field, semantics, version, thứ tự và chính sách gửi lặp. Không được “giảm coupling” bằng cách phát các sự kiện mơ hồ kiểu **EntityUpdated** rồi buộc mọi consumer khôi phục toàn bộ dữ liệu nội bộ để hiểu chuyện gì xảy ra.

### 8.3. Không chia sẻ domain model bằng thư viện chung một cách tùy tiện

Một shared package chứa toàn bộ entity JPA, enum nội bộ, repository và exception nghiệp vụ của nhiều service có thể khiến mọi phiên bản dính chặt. Shared code có thể hữu ích cho phần kỹ thuật ổn định (telemetry, authentication primitives, API contract generated từ schema) nhưng phải tránh biến nó thành cơ sở dữ liệu đối tượng toàn công ty.

Nếu consumer cần dữ liệu của service khác, nên có DTO/event contract rõ và **anti-corruption layer** để ánh xạ về ngôn ngữ nội bộ của consumer, thay vì kéo entity của provider vào làm entity của mình.

### 8.4. Tách command và query theo nhu cầu

Đôi khi Order cần hiển thị tên hàng, ảnh và giá snapshot nhưng không cần truy vấn Catalog trực tiếp cho từng dòng đơn. Có thể lưu snapshot immutable tại thời điểm đặt hàng hoặc read model cập nhật theo event.

Cần ghi rõ snapshot dùng để **hiển thị lịch sử**, không đương nhiên là giá/tồn kho có hiệu lực cho đơn mới. Nếu một quyết định cần giá chính thức hiện tại, phải dùng nguồn được phép quyết định. Đọc dữ liệu bản sao để giảm temporal coupling phải đi kèm policy consistency/freshness tương ứng.

## 9. Cân nhắc coupling đồng bộ và bất đồng bộ

Đối với mỗi dependency, đánh giá:

**Có cần kết quả tức thì không?** Nếu người dùng phải biết ngay thanh toán đã được chấp nhận, API có thể phải đợi Payment với deadline rõ. Nếu chỉ gửi email hoặc cập nhật dashboard thì thường không cần đợi.

**Có thể trả trạng thái chờ không?** Nếu workflow dài, có thể trả ACCEPTED rồi theo dõi PENDING → CONFIRMED/FAILED. API cần định nghĩa ý nghĩa của “thành công” để không làm người dùng hiểu sai.

**Cập nhật có hội tụ được không?** Sự kiện giá/địa chỉ/permission có semantics khác nhau; mỗi loại cần quy tắc event order, version, deduplication và xử lý replay.

**Nếu mất kết nối, ai giữ invariant?** Async không giải quyết bài toán hai service cần cùng commit invariant mạnh. Nên xác định một owner hoặc dùng cơ chế phối hợp có lý do rõ.

**Chi phí debug thế nào?** Với async flow, trace ID/correlation ID, state machine, outbox/consumer lag, dead-letter queue và reconciliation là nhu cầu thật. Không nên chuyển mọi thứ sang event chỉ để “ít gọi REST”.

## 10. Khi nào nên gộp hai service?

Hai service A và B là ứng viên để gộp khi nhiều tín hiệu cùng xuất hiện:

1. Cùng thực thi một invariant transaction mà không có ranh giới sở hữu rõ.
2. Hầu hết lệnh nghiệp vụ của A đều phải gọi B ngay lập tức, và ngược lại.
3. Các thay đổi chính sách luôn cần sửa và deploy cả A lẫn B.
4. A và B cùng sở hữu hoặc truy cập trực tiếp những bảng dữ liệu nội bộ.
5. Test độc lập của A/B khó có ý nghĩa vì quy tắc bị chia giữa hai nơi.
6. Hai service có nhu cầu scale, bảo mật và owner gần như trùng nhau.
7. Việc gộp giảm đáng kể chi phí lỗi mạng/transaction mà không làm service mới chứa nhiều năng lực không liên quan.

Ví dụ “InventoryQuantityService” và “ReservationService” có thể nên ở cùng Inventory Service nếu mọi reservation phải cập nhật số lượng cục bộ theo invariant chung.

**Trước khi gộp**, cần kiểm tra lý do tách ban đầu: yêu cầu pháp lý, isolate sự cố, quyền truy cập riêng hoặc khả năng scale cực khác nhau. Nếu một constraint thực sự tồn tại, có thể giữ tách và cải thiện contract thay vì gộp hoàn toàn.

## 11. Khi nào nên tách một service?

Một service lớn có thể nên tách khi:

- Chứa nhiều năng lực nghiệp vụ ít liên quan, có ngôn ngữ và quy tắc thay đổi khác nhau.
- Hai nhóm cần ownership rõ và độc lập phát hành, nhưng hiện liên tục xung đột trong cùng codebase/release.
- Một chức năng có tải khác biệt lớn và cần scale độc lập để kiểm soát chi phí.
- Có yêu cầu cô lập bảo mật hoặc vận hành rõ ràng.
- Dữ liệu có owner và transactional boundary độc lập, không cần transaction mạnh chung.
- Hợp đồng giữa các phần đủ ổn định, cho phép chuyển thành API/event mà không làm critical path phân mảnh.
- Nhiều thay đổi của một phần buộc phần còn lại trải qua test/deploy dù không liên quan.

Ví dụ Catalog có chức năng quản trị media và giao diện tìm kiếm. Hệ thống có thể cân nhắc tách Search Projection/Indexing khi lưu lượng truy vấn và mô hình index khác đáng kể mô hình quản lý sản phẩm gốc. Nhưng **Catalog vẫn sở hữu dữ liệu mô tả sản phẩm có thẩm quyền**, còn Search chỉ sở hữu bản chiếu/phục vụ truy vấn, với quy trình đồng bộ và rebuild rõ ràng.

**Không tách chỉ vì class vượt một ngưỡng số dòng, file quá lớn hoặc team muốn “đúng microservices”**. Có thể refactor module và interface trước, đo được nhu cầu thực rồi mới chịu chi phí phân tán.

## 12. Phương pháp xác định ranh giới từng bước

### Bước 1 — Liệt kê năng lực và lời hứa nghiệp vụ

Dùng ngôn ngữ của domain experts: “giữ hàng”, “đặt đơn”, “thanh toán”, “xuất hóa đơn”, “giao hàng”, không bắt đầu từ “API Service”, “Database Service”, “Common Utility”.

Định nghĩa cụ thể đầu vào, kết quả thành công, kết quả thất bại và điều người dùng được quyền tin sau khi nhận phản hồi.

### Bước 2 — Lập bản đồ thay đổi nghiệp vụ

Với vài kịch bản quan trọng, xác định thay đổi chính sách sẽ tác động đến quy tắc nào. Nhóm các quy tắc có một lý do thay đổi chung, nhưng tách các quy tắc chỉ ngẫu nhiên nằm trên cùng một endpoint.

Ví dụ “thay đổi thời hạn giữ tồn kho từ 15 thành 20 phút” nên chủ yếu nằm trong Inventory; không nên phải sửa Product và Payment.

### Bước 3 — Xác định owner, invariant và transaction

Vẽ dữ liệu có thẩm quyền, người quyết định trạng thái, những thao tác phải atomic và những dữ liệu chỉ là bản sao đọc. Nếu một invariant trải qua nhiều proposed services, đánh giá lại cách đặt owner.

### Bước 4 — Vẽ dependency graph theo từng use case

Đánh dấu cạnh command/query/event, synchronous/asynchronous, critical path hay background, loại lỗi và retry/timeout. Đánh dấu vòng A ↔ B và những endpoint quá chatty.

### Bước 5 — Xem các ranh giới thay thế

So sánh ít nhất hai phương án: giữ chung trong module/service; tách theo bounded contexts hoặc business capabilities. Chọn dựa trên nhu cầu deploy, tải, ownership, data consistency, failure isolation và chi phí.

Không cần tối đa hóa số service; với một hệ đang nhỏ, lựa chọn tốt có thể là **chỉ một modular monolith** trong giai đoạn đầu.

### Bước 6 — Thử một vertical slice

Triển khai thử một luồng như “đặt hàng và giữ tồn”. Đo dependency runtime, latency, failure handling, số thay đổi cross-service, khả năng contract test và deploy. Đặc biệt kiểm tra trường hợp Payment đã xử lý nhưng response bị mất, hoặc event được gửi lại.

### Bước 7 — Quy định contract và ownership

Viết ngắn gọn cho từng ranh giới: service chịu trách nhiệm gì, không chịu trách nhiệm gì, dữ liệu có thẩm quyền ở đâu, API/event nào được công bố, trạng thái lỗi và freshness được bảo đảm, cách thay đổi schema theo version, ai hỗ trợ incident.

### Bước 8 — Đo sau khi vận hành

Theo dõi số thay đổi cần deploy đồng thời, thời gian phát hành, số hop đồng bộ, retry/error p95/p99, số sự cố xuyên service, chi phí vận hành và khả năng truy vết trách nhiệm. Ranh giới là một giả thuyết thiết kế, cần điều chỉnh khi domain, đội nhóm và tải thay đổi.

## 13. Một mẫu phiếu đánh giá ranh giới

Có thể dùng bảng sau trong buổi thiết kế với team. Đây là **khung trao đổi**, không phải công thức tự động tính điểm:

| Nhóm câu hỏi | Cần trả lời | Bằng chứng tốt |
| --- | --- | --- |
| Mục đích nghiệp vụ | Service có một năng lực chính và phạm vi không chồng lấn? | Mô tả bằng động từ nghiệp vụ, domain glossary |
| Invariant | Điều gì phải đúng trong một commit? Ai quyết định? | Aggregate, transaction, state machine |
| Data ownership | Ai có quyền ghi nguồn dữ liệu chuẩn? | Quyền schema/DB, contract reads/events |
| Change cohesion | Những rule nào thay đổi cùng một lý do? | History của user stories và domain changes |
| Runtime coupling | Có cần nhiều sync calls/hop ngay lúc request? | Trace, critical-path map, timeout budget |
| Change/release coupling | Đổi một service có buộc nâng phiên bản service khác? | Release log, contract tests, rollout plan |
| Failure coupling | Một service chết có làm hỏng chức năng không liên quan? | Fault injection, timeout, bulkhead, graceful degradation |
| Operational ownership | Ai deploy, rollback, on-call và khôi phục dữ liệu? | Team ownership, runbook, SLO |
| Lợi ích chia tách | Có cần scale, bảo mật hoặc phát hành riêng? | Workload, SLA, security requirement, delivery metrics |
| Chi phí chia tách | Có phải thêm broker, Saga, tracing, test, CI/CD? | TCO/effort estimate theo workload và tổ chức |

Cách sử dụng: lấy một proposal như “tách ReservationService khỏi InventoryService”, trả lời từng hàng rồi thảo luận tradeoff. Nếu không thể chỉ ra invariant nào sẽ an toàn hơn, nhóm nào được tự chủ hơn hoặc tải nào được tối ưu nhờ tách, đề xuất có thể đang tăng chi phí mà chưa có giá trị rõ.

## 14. Những sai lầm thường gặp

### Sai lầm 1 — Một bảng dữ liệu tương ứng một service

CRUD services cho Order, OrderLine và OrderStatus thường cần gọi nhau cho gần như mọi thao tác tạo đơn. Điều này tạo coupling cao và data consistency khó hơn. Nên thiết kế theo aggregate và business capability, không theo số bảng.

### Sai lầm 2 — Service nhỏ nhất là service tốt nhất

Microservice không có nghĩa “càng ít class càng tốt”. Quá nhỏ sẽ tăng latency, chi phí triển khai, tracing và phối hợp nhóm; quá lớn sẽ mất độc lập thay đổi. Kích thước chỉ có ý nghĩa khi kết hợp cohesion, coupling và nhu cầu vận hành.

### Sai lầm 3 — Dùng chung database để dễ tích hợp

Cùng cluster hạ tầng có thể chấp nhận trong một số giai đoạn. Nhưng để Order sửa trực tiếp bảng Payment hoặc Inventory phá vỡ data ownership, khiến migration và release phải phối hợp ngầm. Tốt hơn là owner rõ, API/event contract và ranh giới quyền truy cập.

### Sai lầm 4 — Shared library domain để “không trùng lặp”

Gộp mọi entity và enum nghiệp vụ vào một thư viện chung có thể khiến việc đổi schema nhỏ buộc nâng version nhiều service. Lặp lại một vài DTO/mapping ở consumer có thể ít rủi ro hơn shared internal model; contract schema mới là điểm tích hợp.

### Sai lầm 5 — Mọi trao đổi đều đồng bộ

Một request nhỏ có thể trở thành chuỗi gọi dài. Chỉ giữ lời gọi đồng bộ khi kết quả thực sự cần cho cam kết tức thì; công việc nền có thể tách qua event/queue kèm cơ chế vận hành phù hợp.

### Sai lầm 6 — Mọi trao đổi đều bất đồng bộ

Async thêm eventual consistency, duplicate/delayed events, state machine và khó quan sát. Một invariant bắt buộc commit mạnh vẫn cần owner/giao thức phù hợp. “Event-driven” là công cụ, không phải bằng chứng ranh giới tốt.

### Sai lầm 7 — Team boundary = service boundary

Đội nhóm là một yếu tố, nhưng nếu một nghiệp vụ duy nhất bị chia thành nhiều service chỉ để mỗi team sở hữu một phần, các team có thể càng phải phối hợp hơn. Nên tìm domain ownership và những giao diện tương đối ổn định.

### Sai lầm 8 — Chỉ xem coupling ở compile time

Hai service có thể không import bất kỳ class nào của nhau nhưng vẫn cùng query một bảng, phụ thuộc chung broker, yêu cầu deploy đồng thời hoặc cùng hỏng khi một service timeout. Phải đánh giá runtime, data, operations và release coupling.

### Sai lầm 9 — Chia toàn bộ hệ thống trước khi hiểu domain

Ở giai đoạn quy tắc nghiệp vụ chưa ổn định, nhiều service có thể phải thay đổi ranh giới liên tục. Một modular monolith có module boundaries rõ và event/contract nội bộ có thể là bước đi ít rủi ro trước khi tách phần cần độc lập thật sự.

## 15. Bài tập thực hành: thiết kế ranh giới cho sàn bán vé

Giả sử ứng dụng bán vé buổi hòa nhạc có các nhu cầu:

- Hiển thị thông tin buổi diễn và sơ đồ ghế.
- Khóa tạm ghế trong 5 phút khi khách chọn.
- Thanh toán với cổng bên thứ ba.
- Phát hành vé có QR sau khi thanh toán được xác nhận.
- Gửi email chứa vé và theo dõi lượt mở.
- Thống kê số vé bán theo giờ.

### Bài tập 1 — Nhóm theo cohesion

Hãy đề xuất các bounded contexts/capabilities, ví dụ Show Catalog, Seat Inventory/Reservation, Payment, Ticket Issuance, Notification, Analytics. Với từng nhóm, ghi một câu trách nhiệm, dữ liệu có thẩm quyền và invariant chính.

Gợi ý điểm cần tranh luận: Seat và SeatReservation nên chung owner để không bán một ghế hai lần; email mở hay không không nên quyết định vé đã phát hành; Ticket Issuance cần biết thanh toán có được xác nhận đáng tin cậy không.

### Bài tập 2 — Vẽ coupling theo critical path

~~~text
User chọn ghế
    -> SeatReservation.reserve()
    -> Payment.authorize()
    -> TicketIssuance.issue()
    -> Notification.send()
~~~

Hãy xác định bước nào phải có kết quả ngay; bước nào có thể PENDING; bước nào có thể xử lý nền. Đừng quên trường hợp cổng thanh toán thành công nhưng response bị mất.

### Bài tập 3 — Phân tích lỗi

Thảo luận ba sự cố:

1. Seat Reservation trả timeout, nhưng ghế có thể đã được khóa.
2. Payment xác nhận thành công nhưng event đến Ticket Issuance hai lần.
3. Notification ngừng hoạt động trong hai giờ.

Với mỗi trường hợp, định nghĩa idempotency key, source of truth, retry/backoff, trạng thái hiển thị và hành vi khôi phục.

### Bài tập 4 — Lựa chọn tách service

Nếu nhóm chỉ có bốn lập trình viên và đang thử nhu cầu thị trường, hãy so sánh modular monolith có module Seat/Payment/Ticket với việc triển khai sáu microservices ngay. Nêu bằng chứng nào sẽ khiến bạn tách: tăng tải giữ ghế, thay đổi chính sách thanh toán liên tục, yêu cầu security riêng hoặc nhóm ownership độc lập.

**Kết quả mong đợi:** một sơ đồ có ít nhất một owner rõ cho mỗi invariant, danh sách những dependency thiết yếu, những dependency có thể thay bằng event và lời giải thích vì sao ranh giới này giảm coupling mà vẫn giữ cohesion.

## 16. Câu hỏi tự kiểm tra

1. Vì sao hai class cùng dùng database không nhất thiết có cohesion cao?
2. Khi nào “cùng thay đổi thường xuyên” là bằng chứng nên gộp, và khi nào chỉ là hệ quả của coupling hiện tại?
3. Khác biệt giữa **data coupling**, **temporal coupling** và **deployment coupling** là gì? Hãy cho một ví dụ của mỗi loại.
4. Một API có contract ổn định nhưng luôn yêu cầu bảy service khác online để trả lời. Nó còn loại coupling nào?
5. Vì sao Order không nên sửa trực tiếp bảng Reservation dù việc đó có thể giảm một lời gọi HTTP?
6. Nếu Reservation và Stock cần commit trong cùng transaction để tránh oversell, ranh giới nào hợp lý hơn việc tách mỗi bảng thành một service?
7. Event-driven có loại bỏ toàn bộ coupling không? Event contract và retry/deduplication còn những phụ thuộc nào?
8. Vì sao một shared library chứa toàn bộ domain entities có thể cản trở phát hành độc lập?
9. Có phải mỗi bounded context luôn phải trở thành một microservice triển khai riêng? Vì sao?
10. Nếu hai service phải deploy cùng lúc cho mọi thay đổi, bạn sẽ kiểm tra nguyên nhân từ đâu trước khi đề xuất gộp?
11. Một service quá lớn nhưng có cohesion nghiệp vụ cao và nhu cầu scale đồng nhất, có bắt buộc phải tách chỉ vì số dòng code không?
12. Với bài toán bán vé một ghế cuối cùng, phân tích gắn kết giữa thao tác reserve, expire và release; nêu cách xử lý khi Payment timeout.

## 17. Ghi nhớ để thiết kế ranh giới service

- **High cohesion** nghĩa là một service tập trung vào một năng lực nghiệp vụ và các quy tắc/dữ liệu cần để thực hiện nó; tên class giống nhau hoặc cùng framework không đủ để chứng minh.
- **Low coupling** nghĩa là thay đổi, sự cố và triển khai một service ít gây tác động không cần thiết tới service khác; coupling có nhiều chiều: API, runtime, data, transaction, release, operations và tổ chức.
- Bắt đầu bằng **business capabilities, bounded contexts, invariants và data ownership**, sau đó mới xác định API, event và đơn vị triển khai.
- Giữ thao tác cần transaction mạnh trong một owner khi phù hợp. Giao tiếp liên miền phải có contract rõ, idempotency, timeout, xử lý trạng thái không chắc chắn và phương thức reconciliation.
- Một service có thể lớn về số class mà vẫn cohesion cao. Một hệ có nhiều service nhỏ có thể bị coupling rất chặt, trở thành distributed monolith.
- Đánh giá các dấu hiệu bằng **thay đổi thật và trace thật**, thay vì chỉ đếm service hay vẽ mũi tên.
- Chỉ tách khi lợi ích độc lập thay đổi, mở rộng, bảo mật hoặc vận hành lớn hơn chi phí mạng, dữ liệu, kiểm thử và điều phối. Giữ modular monolith là một lựa chọn hợp lệ khi chưa có lý do tách.
- Câu hỏi cuối cùng để đánh giá một ranh giới: **“Một thay đổi nghiệp vụ thuộc trách nhiệm này có thể được hiểu, kiểm thử, phát hành và phục hồi chủ yếu trong chính ranh giới đó hay không?”**
