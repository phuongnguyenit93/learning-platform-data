# Tách vi dịch vụ khi chưa rõ ranh giới nghiệp vụ

## 1. Phản mẫu này là gì?

Trong thiết kế **kiến trúc ứng dụng trên đám mây**, microservices (vi dịch vụ) giúp các thành phần có thể phát triển, triển khai và mở rộng tương đối độc lập. Tuy nhiên, **tách vi dịch vụ khi chưa rõ ranh giới nghiệp vụ** là một phản mẫu kiến trúc: nhóm phát triển chia ứng dụng thành nhiều dịch vụ triển khai riêng khi chưa biết mỗi dịch vụ chịu trách nhiệm cho quy tắc nghiệp vụ, dữ liệu và thay đổi nào.

Kết quả thường là một **distributed monolith** (hệ thống nguyên khối phân tán): trên sơ đồ có nhiều service, nhưng một thay đổi nhỏ phải sửa và triển khai đồng thời nhiều nơi. Hệ thống gánh thêm mạng, độ trễ, lỗi từng phần, xác thực giữa dịch vụ và giám sát phân tán mà không có được tính độc lập đáng kể.

**Ví dụ:** một ứng dụng bán hàng đang chạy ổn định trên một tiến trình. Nhóm chia thành CustomerService, CartService, OrderLineService, PriceService, CouponService và OrderService vì “mỗi bảng có một service”. Mỗi lần khách đặt hàng, OrderService phải gọi nối tiếp nhiều dịch vụ để đọc thông tin, tính giá, áp mã và ghi đơn. Mỗi thay đổi quy tắc chiết khấu lại buộc sửa PriceService, CouponService và OrderService cùng lúc. Việc chia nhỏ này có thể khiến hệ thống kém tin cậy và khó thay đổi hơn phiên bản nguyên khối ban đầu.

> **Ý chính:** Ranh giới service nên phản ánh một khả năng nghiệp vụ có trách nhiệm, dữ liệu và quy tắc tương đối rõ ràng. Số lượng service hay số lượng container không phải thước đo mức độ hiện đại của kiến trúc.

Phản mẫu nằm ở **thời điểm và tiêu chí chia tách**, không nằm ở bản thân microservices. Có nhiều trường hợp tách sớm là hợp lý, chẳng hạn yêu cầu cô lập bảo mật, mô hình tải rất khác nhau hoặc các miền nghiệp vụ đã ổn định với nhóm sở hữu rõ ràng. Quyết định cần dựa trên bằng chứng của hệ thống cụ thể.

## 2. Tại sao ranh giới nghiệp vụ lại quan trọng?

Trong Domain-Driven Design (DDD), **bounded context** là phạm vi mà thuật ngữ, mô hình và quy tắc nghiệp vụ mang một ý nghĩa nhất quán. Chẳng hạn, “sản phẩm” trong quản lý danh mục là nội dung hiển thị, nhưng “mặt hàng” trong một đơn hàng đã chốt là ảnh chụp thông tin và giá tại thời điểm mua. Cố dùng một mô hình Product chung ở mọi nơi có thể khiến các thành phần phải cùng thay đổi khi cách tính giá hoặc cách hiển thị đổi.

Cần phân biệt ba khái niệm:

| Khái niệm | Câu hỏi trả lời | Lưu ý |
|---|---|---|
| **Business capability** (năng lực nghiệp vụ) | Tổ chức cần làm được việc gì, ví dụ nhận đơn hàng hoặc thanh toán? | Là điểm bắt đầu để hiểu trách nhiệm và giá trị |
| **Bounded context** | Trong phạm vi nào mô hình, thuật ngữ, trạng thái và quy tắc có ý nghĩa nhất quán? | Giúp xác định nơi một quy tắc được sở hữu |
| **Service boundary** | Phần mềm nào cần vận hành, triển khai và sở hữu dữ liệu độc lập? | Là quyết định kỹ thuật; không nhất thiết ánh xạ 1:1 với bounded context |

Một bounded context lớn có thể được cài đặt bằng nhiều module trong cùng một ứng dụng. Một microservice có thể phục vụ một phạm vi nhỏ hơn bounded context nếu có lý do rõ ràng. Không nên hiểu DDD là công thức “mỗi danh từ hoặc mỗi bảng = một microservice”.

### 2.1. Những câu hỏi làm lộ ranh giới

Trước khi vẽ một service mới, cần hỏi:

1. **Năng lực nghiệp vụ nào được cung cấp?** Tên như Order, Payment, Inventory thường hữu ích hơn tên thuần kỹ thuật như Validation hoặc DatabaseWrapper, nhưng vẫn cần kiểm chứng thực tế.
2. **Quy tắc và bất biến (invariant) nào phải đúng?** Ví dụ tổng tiền trên một đơn đã xác nhận không được đổi chỉ vì giá niêm yết thay đổi.
3. **Ai có quyền quyết định thay đổi quy tắc?** Chủ nghiệp vụ, nhóm sản phẩm hoặc bộ phận vận hành nào phê duyệt thay đổi?
4. **Dữ liệu nào do phạm vi này sở hữu?** Ai được ghi, ai chỉ được đọc qua hợp đồng hoặc bản sao phục vụ truy vấn?
5. **Thao tác nào cần nhất quán tức thời?** Phần nào có thể cập nhật bất đồng bộ, chấp nhận trạng thái trung gian?
6. **Các thay đổi thường đi cùng nhau hay tách biệt?** Nếu hai “service” luôn đổi cùng nhau, ranh giới hiện tại có thể chưa phù hợp.
7. **Ai trực tiếp xây dựng và vận hành?** Ranh giới service phải phù hợp khả năng sở hữu, trực sự cố và mức độ tự chủ của nhóm.

Đáp án chưa rõ là dấu hiệu nên tiếp tục khám phá domain và giữ các thành phần ở mức module, thay vì lập tức tạo thêm deployment độc lập.

## 3. Các cách chia nhầm thường gặp

| Tiêu chí chia sai hoặc thiếu | Ví dụ | Vì sao dễ gây vấn đề |
|---|---|---|
| **Theo bảng dữ liệu** | UserService, AddressService, OrderRowService | Một giao dịch nghiệp vụ buộc gọi nhiều service; khó xác định owner của quy tắc |
| **Theo CRUD** | CreateOrderService, UpdateOrderService, GetOrderService | Các thao tác trên cùng một vòng đời bị phân tán, tăng coupling và khó giữ invariant |
| **Theo tầng kỹ thuật** | ValidationService, RepositoryService, MappingService | Mỗi request phải đi qua nhiều mạng chỉ để hoàn thành một tác vụ cục bộ |
| **Theo từng màn hình** | CartPageService, CheckoutPageService | Giao diện thay đổi thường xuyên; mô hình dữ liệu và quy tắc nghiệp vụ bị bẻ theo UI |
| **Theo số lập trình viên hoặc số team hiện có** | Mỗi team nhận một service ngẫu nhiên | Khi luồng nghiệp vụ vượt ranh giới team sẽ phải phối hợp liên tục |
| **Theo mong muốn dùng công nghệ mới** | Tách riêng service chỉ để chạy framework khác | Có thêm gánh nặng triển khai mà không giải quyết được nhu cầu nghiệp vụ |
| **Theo kích thước mã nguồn** | Một package 1.000 dòng = một service | Số dòng không đo được tính kết dính (cohesion) hoặc mức phụ thuộc |

Các cách trên không phải lúc nào cũng sai: một dịch vụ truy vấn độc lập hoặc thành phần theo công nghệ có thể hợp lý khi có tải, quyền, SLA hay nhu cầu triển khai riêng. Sai lầm là dùng tiêu chí kỹ thuật làm **căn cứ duy nhất** mà chưa xét luồng nghiệp vụ và quyền sở hữu dữ liệu.

## 4. Cơ chế tạo ra distributed monolith

### 4.1. Gọi đồng bộ liên tiếp (chatty communication)

Giả sử một request đặt hàng phải gọi nối tiếp 7 service. Mỗi lời gọi bổ sung thời gian mạng, mã hóa dữ liệu, xác thực, chờ tài nguyên và nguy cơ timeout. Khi một dịch vụ chậm hoặc lỗi, toàn bộ luồng dễ bị kéo theo.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant O as OrderService
    participant P as PriceService
    participant D as DiscountService
    participant I as InventoryService
    participant L as OrderLineService
    participant X as Shared DB
    C->>O: POST /checkout
    O->>P: Tính giá từng sản phẩm
    P->>X: Đọc bảng giá
    P-->>O: Giá
    O->>D: Tính khuyến mãi
    D->>X: Đọc điều kiện giảm giá
    D-->>O: Giảm giá
    O->>I: Kiểm tra tồn kho
    I->>X: Đọc kho
    I-->>O: Còn hàng
    O->>L: Ghi từng dòng đơn hàng
    L->>X: INSERT
    L-->>O: OK
    O-->>C: Hoàn tất
~~~

Sơ đồ minh họa kiểu phân tách không lành mạnh: nhiều lời gọi đồng bộ trong đường đi quan trọng và các service cùng đọc/ghi cơ sở dữ liệu chung. Nó không khẳng định mọi thiết kế có service Giá hoặc Khuyến mãi đều sai; cần đánh giá tính độc lập, hợp đồng và độ trễ thực tế.

Với chuỗi lời gọi **bắt buộc thành công đồng thời**, xác suất thành công của cả chuỗi có thể giảm khi thêm phụ thuộc. Nếu năm thành phần có xác suất đáp ứng 99,9% độc lập trong một khoảng đo, xác suất lý thuyết cả năm cùng đáp ứng khoảng \(0{,}999^5 \approx 99{,}5\%\). Đây chỉ là minh họa: hệ thống thực có lỗi tương quan, retry, cache và hành vi suy giảm chức năng nên không thể dùng phép nhân này thay cho đo lường SLO.

### 4.2. Dữ liệu dùng chung và nhiều nơi được phép ghi

Một lỗi điển hình là tách 6 service nhưng vẫn cho tất cả truy cập trực tiếp bảng Order, Product hoặc Payment. Khi schema đổi, mọi service có thể bị ảnh hưởng. Khóa bảng, truy vấn chậm hay migration dữ liệu vẫn lan ra toàn hệ thống.

**Sở hữu dữ liệu** không nhất thiết có nghĩa mỗi service phải có một máy chủ DB riêng. Trong giai đoạn chuyển tiếp, có thể cùng dùng một DB engine nhưng tách schema, phân quyền và đường ghi. Điều then chốt là mỗi dữ liệu có một owner nghiệp vụ và các thành phần khác truy cập qua hợp đồng được kiểm soát, không tùy ý sửa bảng của nhau.

### 4.3. Giao dịch phân tán bị tạo ra một cách vô tình

Trong monolith, một số bất biến có thể được bảo vệ trong một transaction cục bộ. Khi chia thành nhiều service, cập nhật đồng thời Đơn hàng, Kho và Thanh toán vượt qua transaction boundary. Không thể giả định chỉ cần gọi ba API là sẽ có tính nguyên tử.

Giải pháp có thể gồm thay đổi phạm vi transaction, dùng reservation, sự kiện và workflow với bù trừ (compensation). Nhưng chúng thêm trạng thái, idempotency, retry và xử lý lỗi từng phần. Nếu chưa hiểu quy tắc nghiệp vụ, khó xác định khi nào được bù trừ và thế nào là kết quả hợp lệ.

### 4.4. Triển khai đồng bộ và vòng phối hợp kéo dài

Một service có pipeline CI/CD riêng không có nghĩa triển khai độc lập. Nếu đổi tên một thuộc tính đòi hỏi sửa cùng lúc năm service, đồng bộ phiên bản API và release trong một cửa sổ bảo trì, tổ chức chỉ chuyển sự phụ thuộc từ compile-time sang runtime.

### 4.5. Quan sát và bảo mật phức tạp hơn

Khi một luồng giao dịch đi qua nhiều service, đội vận hành phải quản lý trace liên dịch vụ, correlation ID, retry storm, circuit breaker, secret, mTLS/TLS, IAM, network policy, rate limit và cấu hình. Những yêu cầu này đều có giá trị khi ranh giới phù hợp; chúng trở thành chi phí vô ích khi service chia nhỏ tùy tiện.

## 5. Dấu hiệu nhận biết trong hệ thống đang vận hành

| Dấu hiệu quan sát | Bằng chứng nên thu thập | Cách diễn giải |
|---|---|---|
| Một thay đổi nhỏ thường sửa nhiều repo | Lịch sử commit, pull request, ticket liên kết | Có thể phân chia theo kỹ thuật thay vì năng lực nghiệp vụ |
| Phải triển khai nhiều service cùng lúc | Release log, dependency matrix, rollback plan | Hợp đồng chưa đủ độc lập hoặc dữ liệu sở hữu mơ hồ |
| Request đi qua nhiều hop chỉ để CRUD | Distributed tracing, service call graph, p95/p99 latency | Ranh giới có thể quá nhỏ hoặc gọi chéo không cần thiết |
| Service truy cập DB/bảng của nhau | Query log, quyền DB, ERD, migration history | Thiếu data ownership, tăng phụ thuộc schema |
| Một service lỗi gây lỗi diện rộng | Incident, timeout, retry metrics, SLO | Thiếu cô lập sự cố và cơ chế suy giảm chức năng |
| Khó biết ai sửa một quy tắc nghiệp vụ | Incident ownership, CODEOWNERS, tài liệu trách nhiệm | Bounded context hoặc vai trò sở hữu chưa rõ |
| Nhóm phát triển dành nhiều thời gian xử lý hạ tầng | Thời gian CI/CD, on-call, vận hành, hóa đơn cloud | Chi phí phân tán lấn át lợi ích của tự chủ |

**Không kết luận chỉ từ một chỉ số.** Có dịch vụ phải gọi nhiều bên vì tích hợp thật sự độc lập. Có hệ thống lớn cần nhiều repository vì chính sách tổ chức. Cần đối chiếu kiến trúc gọi thực tế với quy tắc nghiệp vụ, khả năng thay đổi độc lập và mục tiêu SLO.

## 6. Ví dụ xuyên suốt: phân tách hệ thống thương mại điện tử

Một nhóm muốn hiện đại hóa ứng dụng thương mại điện tử trên cloud. Họ định tách theo các bảng Cart, CartItem, Order, OrderLine, Product, ProductPrice, Coupon, Stock và Payment. Quy tắc “khách được giảm giá khi mua hai sản phẩm thuộc nhóm A nhưng không vượt tổng mức khuyến mãi” sẽ trải khắp nhiều service nhỏ. Khi hoàn tiền, nhóm lại phải điều phối trạng thái từ các service này.

### 6.1. Đi từ quy trình nghiệp vụ

Thay vì lấy tên bảng làm ranh giới, nhóm mô tả những khả năng:

- **Catalog:** quản lý nội dung, phân loại và thông tin hiển thị sản phẩm.
- **Ordering/Checkout:** tạo đơn, khóa ảnh chụp dòng hàng, giá và điều kiện bán đã chấp nhận; quản lý trạng thái đơn.
- **Inventory:** quản lý số lượng có thể bán, giữ/giải phóng tồn kho và điều kiện tồn kho.
- **Payment:** quản lý yêu cầu thanh toán, xác nhận từ nhà cung cấp thanh toán, hoàn tiền và đối soát.
- **Fulfillment:** lên lịch giao, vận chuyển, trạng thái kiện hàng và hoàn trả hàng.

Đây là **các ứng viên bounded context**, chưa phải cam kết phải có đúng năm microservice. Một đội nhỏ có thể triển khai Ordering, Pricing và Promotion thành các module trong một monolith; Inventory hoặc Payment chỉ tách độc lập khi nhu cầu và hợp đồng đã đủ rõ.

### 6.2. Xác định nơi sở hữu dữ liệu và bất biến

| Phạm vi nghiệp vụ | Dữ liệu/chính sách sở hữu | Bất biến tiêu biểu | Cách các phạm vi khác tiêu thụ |
|---|---|---|---|
| Catalog | Nội dung sản phẩm, thuộc tính công bố, danh mục | Thông tin hiển thị đúng phiên bản được công bố | API hoặc sự kiện cập nhật catalog |
| Ordering | Order, order line, trạng thái, giá và điều kiện chốt trong đơn | Đơn đã chốt giữ giá snapshot; chuyển trạng thái hợp lệ | API tra cứu trạng thái, sự kiện đơn được tạo/xác nhận |
| Inventory | Stock ledger, reservation, chính sách phân bổ | Không cấp vượt số lượng có thể bán theo quy tắc đã công bố | Lệnh giữ/giải phóng hàng, sự kiện kết quả |
| Payment | Payment intent, attempt, transaction, refund | Không ghi nhận cùng một khoản thanh toán hai lần do retry | Lệnh thanh toán theo idempotency key, sự kiện kết quả |
| Fulfillment | Shipment, nhãn giao, tracking, xử lý trả hàng | Không phát hàng cho đơn chưa đạt điều kiện giao | Tiêu thụ trạng thái đủ điều kiện từ Ordering |

**Chi tiết quan trọng:** Giá niêm yết có thể do Catalog/Pricing quyết định, nhưng Ordering cần sở hữu bản chụp giá đã chấp thuận trong đơn. Nếu giá niêm yết ngày mai thay đổi, đơn hôm nay không tự thay đổi tổng tiền.

### 6.3. Luồng đặt hàng với hợp đồng rõ hơn

~~~mermaid
flowchart TD
    A[Khách gửi yêu cầu đặt hàng] --> B[Ordering / Checkout]
    B --> C[Kiểm tra quy tắc và chốt snapshot]
    C --> D[Đơn ở trạng thái PENDING]
    D --> E[Inventory: yêu cầu giữ hàng]
    E --> F{Đã giữ được hàng?}
    F -- Không --> G[Ordering: từ chối hoặc hủy đơn]
    F -- Có --> H[Payment: yêu cầu thanh toán]
    H --> I{Thanh toán thành công?}
    I -- Không --> J[Giải phóng giữ hàng]
    J --> G
    I -- Có --> K[Ordering: xác nhận đơn]
    K --> L[Fulfillment: bắt đầu xử lý giao hàng]
~~~

Sơ đồ diễn tả **quy trình nghiệp vụ có nhiều trạng thái**, không ngụ ý mọi mũi tên phải là HTTP đồng bộ. Có thể dùng event, queue và workflow coordinator, hoặc giữ một số bước trong cùng ứng dụng, tùy tính nhất quán, thời gian phản hồi và khả năng khôi phục.

Khi dùng cơ chế bất đồng bộ, cần thiết kế ít nhất:

1. **Idempotency:** lệnh giữ hàng/thanh toán và consumer có thể nhận lại thông điệp mà không gây trừ kho hay thu tiền hai lần.
2. **Transactional outbox hoặc cơ chế tương đương:** lưu thay đổi trạng thái nghiệp vụ và bản ghi cần phát sự kiện trong cùng một transaction cục bộ, sau đó phát tin đáng tin cậy.
3. **Correlation ID và trạng thái theo dõi:** lần theo một đơn hàng xuyên các thành phần và phân biệt PENDING, CONFIRMED, CANCELLED, REFUND_PENDING...
4. **Retry, timeout và dead-letter:** xử lý sự cố tạm thời nhưng tránh retry vô hạn hoặc bão retry.
5. **Compensation có ý nghĩa nghiệp vụ:** nếu đã giữ kho mà thanh toán thất bại thì giải phóng giữ hàng; nếu đã thu tiền nhưng bước sau không thể hoàn tất có thể cần hoàn tiền theo quy định.

Không nên xem **Saga** là cách làm hệ thống tự động có transaction ACID xuyên mọi dịch vụ. Saga phối hợp các transaction cục bộ và hành động bù trừ, có thể có trạng thái trung gian quan sát được; một hành động thực tế như gửi email hoặc giao hàng có thể không hoàn tác hoàn toàn.

## 7. Tìm ranh giới bằng khám phá domain

Để tránh phản mẫu này, kiến trúc sư cùng product owner, chuyên gia nghiệp vụ, kỹ sư, vận hành và bảo mật thực hiện những bước sau.

### 7.1. Bắt đầu từ sự kiện nghiệp vụ

Trong một buổi Event Storming hoặc workshop tương tự, liệt kê:

- **Event:** Đơn hàng được tạo, Hàng đã được giữ, Thanh toán thất bại, Đơn bị hủy, Hàng đã giao.
- **Command:** Tạo đơn, Giữ hàng, Thu tiền, Hủy đơn, Tạo vận đơn.
- **Policy/rule:** Chỉ xác nhận đơn khi đủ điều kiện; hoàn tiền theo trạng thái thanh toán; không giao hàng cho đơn chưa sẵn sàng.
- **Actor:** khách hàng, kho, kế toán, cổng thanh toán, đối tác vận chuyển.
- **Hotspot:** các quy tắc chưa thống nhất, dữ liệu có owner tranh chấp hoặc trạng thái chưa rõ.

Từ đó tìm các cụm quy tắc có ngôn ngữ riêng, vòng đời riêng và chủ sở hữu ổn định. Đánh dấu chỗ quy trình đi xuyên cụm để thiết kế hợp đồng giao tiếp.

### 7.2. Phân tích change coupling

Đọc các yêu cầu đã làm, bản ghi sửa lỗi và thay đổi gần đây để xem phần nào thường thay đổi cùng nhau. Ví dụ, tính khuyến mãi và tổng tiền đơn có thể luôn cần được cập nhật nhất quán trong bước checkout; tách chúng thành hai triển khai độc lập chưa chắc đem lại giá trị.

**Change coupling** là tín hiệu, không phải bằng chứng tuyệt đối: hai module có thể đổi cùng nhau trong một giai đoạn ra mắt sản phẩm mới, sau đó tách nhịp phát triển. Cần kết hợp với mô hình nghiệp vụ và tốc độ thay đổi dự kiến.

### 7.3. Phân tích dữ liệu và tính nhất quán

Với mỗi thao tác, xác định:

- Dữ liệu nào phải cùng đúng trong **một transaction**?
- Dữ liệu nào có thể cập nhật theo sự kiện trong vài giây hoặc vài phút?
- Người dùng thấy gì khi bước tiếp theo chưa hoàn tất?
- Khi có lỗi từng phần, có thể retry hoặc bù trừ không?
- Ai được sửa trạng thái và bản ghi nào?

Nếu phải có transaction chặt xuyên một nhóm dữ liệu và chưa có phương án nghiệp vụ cho nhất quán cuối cùng, đó là dấu hiệu nên **giữ các quy tắc liên quan trong cùng một ranh giới triển khai** ở giai đoạn hiện tại.

### 7.4. Kiểm tra tính tự chủ của nhóm

Một microservice độc lập cần người chịu trách nhiệm từ phát triển đến giám sát, trực sự cố, dữ liệu và vòng đời API. Việc lập nhiều nhóm “sở hữu service” nhưng mỗi thay đổi đều phải chờ nhóm khác không tạo ra tự chủ thực chất.

### 7.5. Tạo context map và hợp đồng

Dùng context map để chỉ rõ quan hệ như upstream/downstream, hợp đồng sự kiện, API và chỗ cần lớp chống phụ thuộc (anti-corruption layer). Hợp đồng nên dùng **ngôn ngữ nghiệp vụ** thay vì để lộ schema nội bộ.

Ví dụ, hợp đồng tốt có thể là:

~~~json
{
  "eventType": "InventoryReservationConfirmed",
  "eventVersion": 1,
  "eventId": "evt-example-123",
  "orderId": "ord-example-456",
  "reservationId": "res-example-789",
  "occurredAt": "2026-01-10T12:00:00Z"
}
~~~

Đây là payload minh họa, chưa phải hợp đồng đầy đủ. Khi triển khai cần quy định schema validation, nhận dạng người gửi, versioning, xử lý trùng và thứ tự sự kiện ở mức phù hợp. Bên tiêu thụ nên dựa vào ý nghĩa “đã giữ hàng” thay vì tự đọc các hàng trong bảng StockLedger.

## 8. Modular monolith: một điểm khởi đầu hữu ích

**Modular monolith** là một ứng dụng triển khai cùng nhau nhưng chia module theo ranh giới nghiệp vụ rõ, giới hạn phụ thuộc và bảo vệ dữ liệu nội bộ. Nó cho phép nhóm làm rõ domain và cải tiến mô hình mà chưa trả giá cho nhiều môi trường runtime độc lập.

~~~mermaid
flowchart TB
    U[Web / API] --> M
    subgraph M[Ứng dụng triển khai chung]
      O[Module Ordering]
      I[Module Inventory]
      P[Module Payment]
      F[Module Fulfillment]
      O --> I
      O --> P
      O --> F
    end
    O --> DO[(Dữ liệu Ordering)]
    I --> DI[(Dữ liệu Inventory)]
    P --> DP[(Dữ liệu Payment)]
    F --> DF[(Dữ liệu Fulfillment)]
~~~

Sơ đồ thể hiện **quyền sở hữu logic** của dữ liệu; các vùng dữ liệu có thể nằm trên cùng một máy chủ DB trong giai đoạn đầu. Điều quan trọng là module khác không sửa trực tiếp cấu trúc nội bộ. Mũi tên gọi module cũng phải tuân theo API/hợp đồng có nghĩa; không mở đường gọi tùy ý mọi lớp của nhau.

Trong Java, có thể tổ chức theo domain:

~~~text
com.example.commerce
  ordering
    api/
    application/
    domain/
    infrastructure/
  inventory
    api/
    application/
    domain/
    infrastructure/
  payments
    api/
    application/
    domain/
    infrastructure/
  fulfillment
    api/
    application/
    domain/
    infrastructure/
~~~

Quy ước:

- Module Ordering gọi giao diện công khai của Inventory hoặc Payment; không import thẳng repository và entity nội bộ của module khác.
- Quy tắc nghiệp vụ nằm gần mô hình chịu trách nhiệm; không gom mọi logic vào một GlobalBusinessService.
- Schema và migration có owner; nếu dùng chung DB thì phân quyền hoặc kiểm tra phụ thuộc để ngăn ghi chéo.
- Kiểm tra phụ thuộc module bằng quy tắc kiến trúc và review; có thể áp dụng Java modules, ArchUnit hoặc các cơ chế khác phù hợp nền tảng.

Modular monolith **không tự động bảo đảm kiến trúc tốt**. Một ứng dụng với rất nhiều package nhưng dùng chung mutable state và các repository toàn cục vẫn có thể rối. Ranh giới phải được bảo vệ trong code và trong cách làm việc của nhóm.

### 8.1. So sánh hai lựa chọn

| Tiêu chí | Modular monolith | Microservices với ranh giới đã rõ |
|---|---|---|
| Triển khai | Một release chính | Các service có thể phát hành độc lập |
| Giao tiếp giữa phạm vi | Thường là gọi nội bộ, ít overhead mạng | Mạng/API/event, có lỗi từng phần |
| Dữ liệu và transaction | Thuận tiện cho transaction cục bộ | Cần xác định data ownership và nhất quán liên dịch vụ |
| Mở rộng | Thường scale cả ứng dụng; có thể tối ưu module ở mức mã | Có thể scale riêng theo nhu cầu thực |
| Vận hành | Pipeline, alert, trace thường đơn giản hơn | Nhiều pipeline, secret, IAM, logs, tracing và on-call |
| Khả năng học domain | Sửa ranh giới dễ hơn khi còn ở mức module | Ranh giới sai gây chi phí di chuyển API và dữ liệu |
| Điểm mạnh chính | Giảm chi phí phối hợp kỹ thuật khi nghiệp vụ còn thay đổi | Tự chủ và cô lập khi domain, team và tải đã đủ rõ |

Không nên chọn modular monolith chỉ vì “doanh nghiệp nhỏ” hoặc microservices chỉ vì “doanh nghiệp lớn”. Cần so sánh theo đội ngũ, SLO, tần suất thay đổi, mô hình tải và mức độc lập cần đạt.

## 9. Khi nào tách microservice là quyết định có căn cứ?

Một phạm vi là ứng viên tách tốt khi có phần lớn các dấu hiệu:

- **Nghiệp vụ:** quy tắc, thuật ngữ, vòng đời và chủ sở hữu của phạm vi tương đối ổn định.
- **Dữ liệu:** nguồn ghi có owner rõ; hợp đồng với bên ngoài không bắt bên ngoài biết schema nội bộ.
- **Thay đổi:** có nhu cầu release với nhịp khác các phạm vi còn lại và có thể tương thích phiên bản trong thời gian chuyển tiếp.
- **Tải hoặc SLO:** yêu cầu scale, latency, availability, vùng triển khai hoặc cô lập sự cố khác biệt và đo được.
- **Bảo mật/tuân thủ:** có yêu cầu ranh giới tin cậy, quyền truy cập hoặc dữ liệu riêng đáng để trả chi phí vận hành.
- **Đội ngũ:** có năng lực xây dựng, bảo trì, quan sát và chịu trách nhiệm service sau triển khai.
- **Kiểm thử:** có thể xác minh đầu vào/đầu ra của service độc lập và hợp đồng với các bên liên quan.

Đây là các **tiêu chí đánh giá**, không phải danh sách bắt buộc phải đủ hết. Ví dụ, một thành phần xử lý dữ liệu nhạy cảm có thể cần cô lập vì yêu cầu bảo mật mạnh, dù team còn nhỏ; một module tính toán nặng có thể cần scale riêng dù cách dùng chưa phong phú.

### 9.1. Câu hỏi định lượng trước khi tách

| Chiều đánh giá | Dữ liệu trước thay đổi | Kết quả mong muốn sau thay đổi |
|---|---|---|
| Lead time | Thời gian từ commit đến production của thay đổi độc lập | Giảm thời gian chờ release do phần khác |
| Change failure rate | Tần suất thay đổi gây lỗi, phạm vi ảnh hưởng | Giảm blast radius hoặc giảm số lỗi lan chéo |
| MTTR | Thời gian phát hiện và khôi phục sự cố | Khoanh vùng sự cố nhanh hơn |
| Runtime | p95/p99, throughput, CPU/memory, queue backlog | Scale phần có nút thắt thật thay vì toàn ứng dụng |
| Coupling | Số repo, API và nhóm phải sửa trên một thay đổi | Giảm thay đổi đồng thời |
| Cost | Compute, storage, egress, observability, CI/CD, on-call | Tổng chi phí phù hợp giá trị thu được |
| Reliability | SLO, error budget, nguyên nhân cascading failure | Độ tin cậy có thể đo và có phương án suy giảm |

Đừng đặt ngưỡng chung “trên N request/giây thì phải dùng microservice”. Một monolith được tối ưu có thể phục vụ tải lớn; một service nhỏ nhưng yêu cầu cô lập rất cao lại có thể cần tách sớm.

## 10. Lộ trình tách dần an toàn

Khi đã có lý do tách, phương pháp tăng dần giúp kiểm chứng giả thuyết trước khi tăng chi phí vận hành.

### Bước 1 — Ghi rõ vấn đề và đường cơ sở

Viết một **Architecture Decision Record (ADR)** nêu vấn đề cụ thể: chẳng hạn đơn vị xử lý ảnh phải scale gấp mười nhưng monolith chỉ tăng tải ở một phần; hoặc release của mảng thanh toán phải tuân theo quy trình phê duyệt riêng. Ghi baseline về hiệu năng, lỗi, chi phí, tần suất release và phụ thuộc hiện tại.

### Bước 2 — Làm sạch ranh giới ở trong ứng dụng

Gom quy tắc liên quan về cùng module, tạo API nội bộ ổn định, ngăn sửa trực tiếp dữ liệu của nhau. Mục tiêu là có thể trả lời: **thay đổi nghiệp vụ X sẽ chạm vào module nào?**

### Bước 3 — Chọn một phạm vi tương đối độc lập để thử

Ưu tiên phạm vi có kết quả đo được, dữ liệu sở hữu rõ và ít phải transaction chặt với phần còn lại. Tránh tách cùng lúc toàn bộ hệ thống hoặc bắt đầu bằng luồng phụ thuộc nhiều nhất khi đội chưa có kinh nghiệm vận hành phân tán.

### Bước 4 — Thiết kế hợp đồng và dữ liệu

Xác định command, query, event, schema, versioning, quyền, SLA/SLO, idempotency, timeout và cách phát hiện lỗi. Chọn cách chuyển dữ liệu phù hợp: đồng bộ có kiểm soát, batch, CDC hoặc quy trình chuyển owner. Nếu tạm thời dual-write, phải có cơ chế xử lý lệch dữ liệu; dual-write không có kiểm soát rất dễ gây sai lệch khi một bên ghi thành công còn bên kia thất bại.

### Bước 5 — Tách bằng Strangler Fig hoặc một lát cắt chức năng

Định tuyến dần một nhóm request hoặc luồng nghiệp vụ sang thành phần mới, với quan sát và rollback. Có thể triển khai feature flag, routing theo đối tượng hoặc chuyển đổi một endpoint riêng. Không sao chép vô thời hạn logic nghiệp vụ ở hai hệ thống.

~~~mermaid
flowchart LR
    C[Client] --> G[API gateway / Router]
    G -->|Luồng đã chuyển| N[Service mới]
    G -->|Luồng còn lại| O[Ứng dụng cũ]
    N --> D[(Dữ liệu do service mới sở hữu)]
    O --> L[(Dữ liệu legacy)]
    O -. Hợp đồng có kiểm soát .-> N
~~~

Khi đã chuyển quyền sở hữu dữ liệu, cần giảm dần đường đọc/ghi chéo và loại bỏ logic trùng lặp. Bước cuối chỉ đóng được khi không còn consumer hoặc writer phụ thuộc khả năng cũ.

### Bước 6 — Xác minh tính độc lập, rồi mới tách tiếp

Đo xem service mới có thực sự:

1. Deploy mà không buộc deploy đồng thời các phần khác.
2. Sở hữu và thay đổi dữ liệu/hợp đồng trong phạm vi được quản lý.
3. Chịu lỗi cục bộ hoặc suy giảm có kiểm soát.
4. Được team chịu trách nhiệm quan sát và xử lý sự cố.
5. Đạt mục tiêu đã đặt về tải, độ trễ, bảo mật hoặc tốc độ thay đổi.

Nếu không đạt, phân tích lại ranh giới. **Tạo thêm service chưa chắc giải quyết được coupling của service hiện tại.**

## 11. Nếu đã lỡ xây distributed monolith thì xử lý thế nào?

Không nên mặc định phải viết lại toàn bộ. Trước hết đo đường gọi thực tế và nguyên nhân phải thay đổi cùng nhau, sau đó chọn một hoặc nhiều biện pháp:

| Vấn đề đang có | Biện pháp cải thiện | Rủi ro/điều kiện |
|---|---|---|
| Nhiều service luôn phải sửa và release chung | Xem xét **gộp lại** thành một module hoặc một deployment có trách nhiệm nhất quán | Cần kế hoạch chuyển tuyến, xử lý dữ liệu, ownership và rollback |
| Truy cập chéo DB | Xác định data owner, đóng đường ghi trực tiếp, tạo API/event và chuyển quyền dần | Giai đoạn chuyển tiếp cần đồng bộ và đối soát |
| Nhiều lời gọi đồng bộ chỉ để lấy dữ liệu phụ | Dùng read model, snapshot hoặc cache có kiểm soát | Phải công bố độ mới dữ liệu và cơ chế làm mới |
| Thay đổi hợp đồng gây lỗi liên tục | Contract test, schema evolution, tương thích ngược, versioning | Cần quản lý vòng đời phiên bản |
| Một lỗi nhỏ lan ra toàn bộ request | Timeout, retry có giới hạn, bulkhead, circuit breaker, graceful degradation | Không dùng retry để che lỗi nghiệp vụ cố định |
| Không biết nơi xử lý một quy tắc | Workshop domain, lập context map, giao owner, chuyển logic về đúng module | Cần sự thống nhất giữa nghiệp vụ và kỹ thuật |
| Quá nhiều hạ tầng cho lợi ích ít | Hợp nhất pipeline/runtime hoặc trở về modular monolith khi có cơ sở | Đánh giá chi phí di chuyển và khả năng vận hành |

**Gộp dịch vụ là một lựa chọn kiến trúc bình thường** nếu nó làm giảm phụ thuộc và chi phí mà vẫn đáp ứng yêu cầu. Mục tiêu là ranh giới đúng và khả năng thay đổi phù hợp, không phải liên tục tăng số lượng service.

### Một ví dụ chữa lỗi

Ba dịch vụ Coupon, DiscountRule và OrderTotal luôn được cập nhật cùng nhau mỗi khi chính sách giá đổi. Chúng chia sẻ bảng promotion và gọi đồng bộ trong mỗi lần checkout.

Giải pháp khả thi là gom ba chức năng về một **Pricing/Promotion module** thuộc phạm vi checkout hoặc có hợp đồng nghiệp vụ rõ ràng. Trong lần tái cấu trúc đầu, module có thể vẫn chạy cùng ứng dụng. Chỉ cân nhắc triển khai độc lập khi nhóm có lý do riêng về tải, owner và contract. Nếu nhiều kênh (web, quầy hàng, ứng dụng đối tác) cần cùng chính sách giá và Pricing có vòng đời rõ, một service Pricing độc lập cũng có thể hợp lý; quyết định phụ thuộc vào domain thực tế.

## 12. Đánh giá theo nguyên tắc Well-Architected

Phản mẫu tách sai ranh giới thường gây thiệt hại trên nhiều trụ cột:

| Trụ cột | Rủi ro khi chia sai | Cách đánh giá/phòng tránh |
|---|---|---|
| **Operational Excellence** | Nhiều pipeline, môi trường, alert, nhóm trực; xử lý thay đổi nhỏ cần phối hợp lớn | Theo dõi lead time, release coupling, incident ownership; chuẩn hóa nhưng không nhân service vô cớ |
| **Security** | Tăng endpoint, danh tính máy, secret và đường mạng; quyền truy cập dữ liệu chồng chéo | Threat modeling theo ranh giới tin cậy, least privilege, data ownership và audit |
| **Reliability** | Lỗi từng phần, timeout, retry storm, transaction phân tán và cascading failure | SLO theo hành trình người dùng, trace, fault injection phù hợp, thiết kế idempotency và suy giảm chức năng |
| **Performance Efficiency** | Chậm vì quá nhiều network hop; scale nhầm thành phần | Phân tích p95/p99, critical path, saturation, contention và tải từng capability |
| **Cost Optimization** | Chi phí nền của container, cluster, API gateway, egress, logging và vận hành tăng | Tính tổng chi phí vòng đời và so với lợi ích triển khai/scale độc lập |
| **Sustainability** | Tài nguyên luôn bật cho nhiều service ít tải, telemetry và truyền dữ liệu không cần thiết | Right-size, tránh dư thừa idle capacity và giảm trao đổi dữ liệu vô ích |

Đặc biệt, việc tách service sai có thể tạo **ảo giác an toàn**: số lượng deployment tăng nhưng mỗi yêu cầu vẫn phụ thuộc tất cả dịch vụ, nên khả năng phục vụ toàn luồng không được cải thiện.

## 13. Mẫu ADR cho quyết định chưa tách service

Ví dụ tài liệu quyết định ở một nhóm thương mại điện tử:

~~~markdown
# ADR-014: Giữ Pricing và Promotion trong module Checkout

## Bối cảnh
- Chính sách khuyến mãi và tổng tiền đơn thường thay đổi cùng nhau.
- Checkout cần tính tổng tiền nhất quán khi khách chấp thuận mua.
- Nhóm vận hành chưa có yêu cầu scale hoặc SLO riêng cho Pricing.
- Việc tách PriceService và CouponService sẽ thêm 2 hop đồng bộ.

## Quyết định
Giữ Pricing và Promotion là các module rõ ranh giới bên trong
ứng dụng Checkout. Dữ liệu snapshot giá đã chốt do Ordering sở hữu.

## Hệ quả
- Có thể thay đổi quy tắc và kiểm thử trong một release.
- Chưa thể triển khai Pricing độc lập.
- Cần kiểm soát import và sở hữu dữ liệu để tránh coupling nội bộ.

## Điều kiện xem xét lại
- Nhiều kênh bán hàng cần cùng hợp đồng định giá có chủ sở hữu rõ.
- Có số liệu chứng minh nhu cầu scale hoặc triển khai Pricing riêng.
- Có phương án cho tính nhất quán, latency, observability và rollback.

## Tiêu chí xác minh
- Checkout giữ đúng tổng tiền ở thời điểm chốt đơn.
- Thay đổi khuyến mãi không yêu cầu sửa các module không liên quan.
- p95/p99 và tỉ lệ lỗi checkout đạt SLO do nhóm thống nhất.
~~~

ADR chỉ là công cụ lưu quyết định và giả định. Khi dữ liệu hoặc nhu cầu thay đổi, nhóm có thể làm ADR mới để tách một service, sau khi xác định được lợi ích và chi phí.

## 14. Bài tập phân tích kiến trúc

**Tình huống:** Một nhóm 8 kỹ sư quản lý ứng dụng đặt lịch dịch vụ. Bản đầu có một ứng dụng Java và một DB, phục vụ 30.000 lượt đặt lịch/ngày. Họ dự kiến chia thành UserService, AppointmentService, TimeSlotService, BookingStatusService, EmailService, NotificationTemplateService và PaymentService vì mỗi tên tương ứng với một bảng. Chưa có số liệu tải hoặc mục tiêu triển khai riêng. Một quy tắc mới yêu cầu việc hủy lịch không được hoàn tiền nếu đã quá thời hạn quy định.

**Yêu cầu phân tích:**

1. Liệt kê ít nhất bốn câu hỏi về nghiệp vụ và chủ sở hữu cần làm rõ trước khi chọn ranh giới.
2. Xác định những cặp service có khả năng bị chia quá nhỏ hoặc bị gắn chặt qua transaction.
3. Đề xuất cách tổ chức module ban đầu và hợp đồng giữa Booking, Payment và Notification.
4. Nêu một tình huống có bằng chứng đủ mạnh để tách một module thành microservice.
5. Đưa ra ba chỉ số đo xem thay đổi kiến trúc có tạo giá trị.

**Gợi ý lời giải:**

- Cần hiểu vòng đời lịch hẹn, quy tắc đổi/hủy, điều kiện hoàn tiền, ai sở hữu khung giờ, làm sao tránh trùng chỗ, và điều gì xảy ra khi thanh toán thất bại.
- Appointment, TimeSlot và BookingStatus có thể thuộc một bounded context **Booking** nếu cùng bảo vệ việc không đặt trùng và chuyển trạng thái hợp lệ. User/Profile và Payment có thể có mô hình riêng; phải kiểm tra nhu cầu thực tế.
- Có thể bắt đầu với modular monolith chứa Booking, Customer, Payment Integration và Notification. Booking phát sự kiện BookingCancelled; logic quyết định khoản hoàn tiền cần có owner rõ theo quy tắc kinh doanh; Payment xử lý thao tác hoàn tiền idempotent. Notification tiêu thụ sự kiện và gửi thông báo có retry. Không nhất thiết triển khai từng module thành service.
- Nếu Notification tạo tải gửi lớn, cần cô lập lỗi từ nhà cung cấp email và có SLO khác, nhóm có thể tách riêng worker xử lý thông báo cùng hàng đợi. Nếu thanh toán chịu yêu cầu bảo mật hoặc phát hành độc lập có căn cứ, cũng có thể tách Payment.
- Đo lead time thay đổi chính sách hủy, tỷ lệ sự cố và p95/p99 hành trình đặt/hủy lịch; bổ sung chi phí hạ tầng, số thành phần phải release cùng nhau.

**Điểm cần tránh trong bài tập:** Không dùng riêng con số 30.000 lượt/ngày để kết luận phải hoặc không được dùng microservices. Lựa chọn còn phụ thuộc mô hình tải đỉnh, transaction, đội ngũ, SLO và mức cô lập cần thiết.

## 15. Checklist trước khi vẽ một microservice mới

- [ ] Đã mô tả được năng lực nghiệp vụ và người sở hữu quy tắc của phạm vi này?
- [ ] Các thuật ngữ, trạng thái và invariant trong phạm vi có ý nghĩa nhất quán?
- [ ] Biết dữ liệu nào do phạm vi này sở hữu, ai được ghi, ai được đọc và qua hợp đồng nào?
- [ ] Xác định được thao tác cần transaction cục bộ và các bước có thể chấp nhận nhất quán cuối cùng?
- [ ] Đã kiểm tra change coupling và các đường gọi đồng bộ trong hành trình người dùng?
- [ ] Có lý do đo được về phát hành, scale, bảo mật, cô lập sự cố hoặc quyền sở hữu để tách?
- [ ] Nhóm chịu trách nhiệm có khả năng triển khai, giám sát, trực sự cố và quản lý vòng đời service?
- [ ] API/event có chiến lược version, timeout, idempotency, retry và kiểm thử hợp đồng phù hợp?
- [ ] Đã cân nhắc modular monolith hoặc giữ cùng deployment trong khi domain chưa ổn định?
- [ ] Có baseline, phương án chuyển dần, quan sát, rollback và tiêu chí quyết định sau thử nghiệm?

## 16. Kết luận

Tách vi dịch vụ khi chưa rõ ranh giới nghiệp vụ biến những phụ thuộc bên trong ứng dụng thành phụ thuộc qua mạng, làm tăng độ trễ, độ phức tạp vận hành và chi phí mà chưa chắc đem lại khả năng tự chủ. Kiến trúc tốt bắt đầu từ **nghiệp vụ, invariant, quyền sở hữu dữ liệu, nhịp thay đổi và nhu cầu vận hành**; ranh giới triển khai được lựa chọn sau đó.

Với hệ thống mới hoặc domain còn biến động, **modular monolith có ranh giới được bảo vệ** thường là bước thử nghiệm hợp lý. Khi có bằng chứng về nhu cầu phát hành, mở rộng hoặc cô lập riêng, hãy tách từng phạm vi qua hợp đồng rõ và xác minh hiệu quả sau tách. Mục tiêu cuối cùng là một kiến trúc cloud đáp ứng yêu cầu nghiệp vụ và cân bằng **độ tin cậy, bảo mật, khả năng mở rộng, chi phí, hiệu năng và vận hành** theo tinh thần Well-Architected.
