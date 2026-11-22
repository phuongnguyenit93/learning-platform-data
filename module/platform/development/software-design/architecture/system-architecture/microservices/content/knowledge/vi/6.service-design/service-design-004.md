# Quản lý trạng thái nghiệp vụ và trạng thái phiên làm việc trong Microservices

## 1. Vì sao cần phân biệt hai loại trạng thái?

Một khách hàng mở website thương mại điện tử, đăng nhập, thêm sản phẩm vào giỏ, đặt đơn, thanh toán và quay lại sau vài ngày để xem đơn đã giao chưa. Hệ thống phải nhớ nhiều thông tin, nhưng **không phải thông tin nào cũng có cùng ý nghĩa, thời hạn sống hoặc nguồn sở hữu**.

Chẳng hạn:

- Đơn **ORD-1001 đã được thanh toán** là sự thật nghiệp vụ quan trọng. Nó phải còn đúng khi khách đóng trình duyệt, hết phiên đăng nhập, ứng dụng restart hoặc một instance bị thay thế.
- Khách **đang đăng nhập trong trình duyệt này** là trạng thái của phiên làm việc/xác thực. Nó có thể hết hạn, bị thu hồi hoặc thay đổi độc lập với tình trạng đơn hàng.
- Người dùng **đang nhập địa chỉ vào biểu mẫu nhưng chưa bấm lưu** có thể chỉ là trạng thái giao diện tạm thời.
- Một instance đang xử lý request có **biến local, thread và cache trong RAM**. Những dữ liệu này có thể mất khi process kết thúc và không tự được chia sẻ cho instance khác.

Nếu trộn các trạng thái đó, hệ thống dễ gặp những lỗi: đơn hàng biến mất khi logout, request vào replica khác không thấy session, callback thanh toán đến sau khi session hết hạn không được xử lý, hoặc retry tạo hai đơn và thu tiền hai lần.

Bài học này tập trung vào **thiết kế dịch vụ**: phân loại trạng thái, chọn nơi lưu đúng, bảo vệ tính nhất quán, vận hành nhiều instance và xử lý các tình huống lỗi trong kiến trúc phân tán.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **business state**, **session state**, **request/UI state** và **runtime state**.
2. Chọn nơi lưu trạng thái theo yêu cầu về tính bền vững, bảo mật, hiệu lực và trách nhiệm sở hữu.
3. Thiết kế ứng dụng có nhiều instance mà không phụ thuộc session hay dữ liệu nghiệp vụ trong RAM của một process.
4. Mô hình hóa vòng đời đơn hàng bằng các trạng thái và chuyển trạng thái hợp lệ.
5. Hiểu idempotency, optimistic locking, transactional outbox và eventual consistency trong cập nhật nghiệp vụ.
6. So sánh server-side session, token-based authentication và session affinity.
7. Phân tích tác động của timeout, logout, restart, retry, nhiều thiết bị và nhiều tab trình duyệt.

## 2. Bốn lớp trạng thái thường gặp

Không chỉ có hai loại. Khi thiết kế một API, hãy phân biệt ít nhất bốn lớp sau.

| Loại | Câu hỏi đại diện | Ví dụ | Nguồn sở hữu thường gặp | Thời gian tồn tại |
| --- | --- | --- | --- | --- |
| **Trạng thái nghiệp vụ** (business/domain state) | Nghiệp vụ đã xảy ra điều gì và còn nghĩa vụ gì? | Order=PAID, reservation đã giữ, refund đang chờ | Bounded Context sở hữu nghiệp vụ | Theo vòng đời nghiệp vụ, quy định lưu trữ/audit |
| **Trạng thái phiên** (session/authentication state) | Yêu cầu hiện tại thuộc phiên nào, đã xác thực chưa? | sessionId, đăng nhập, thiết bị được tin cậy | Identity/Auth hoặc thành phần quản lý session | Thường ngắn hạn, có TTL hoặc cơ chế thu hồi |
| **Trạng thái giao diện/yêu cầu** (UI/request state) | Người dùng đang nhập gì, request đang thực hiện đến đâu? | Ô tìm kiếm, form chưa lưu, request context | Browser/client hoặc request handler | Từ vài mili giây đến hết tương tác, trừ khi chủ động lưu |
| **Trạng thái runtime** (instance/process state) | Bản chạy ứng dụng đang có tài nguyên gì? | Heap, thread pool, connection pool, local cache | Một instance cụ thể | Theo vòng đời process/container |

**Nguyên tắc phân biệt:** phân loại dựa vào **ý nghĩa và hợp đồng tồn tại**, không dựa duy nhất vào kiểu dữ liệu hay công nghệ lưu. Một chuỗi JSON trong Redis có thể là session; một chuỗi khác là snapshot nghiệp vụ. Cùng một storage không làm hai đối tượng có cùng trách nhiệm.

Đôi khi một thực thể thay đổi loại theo thiết kế. Ví dụ giỏ hàng ban đầu có thể là dữ liệu tạm trong trình duyệt; khi doanh nghiệp cam kết lưu giỏ xuyên thiết bị và gửi nhắc mua hàng, giỏ trở thành một khả năng nghiệp vụ có nguồn sở hữu và chính sách lưu trữ cụ thể.

## 3. Trạng thái nghiệp vụ: dữ liệu thể hiện sự thật và nghĩa vụ

**Trạng thái nghiệp vụ** mô tả tình hình hiện tại của một đối tượng hoặc quy trình theo các quy tắc domain. Nó quyết định hành vi tiếp theo được phép xảy ra.

Ví dụ với Order:

~~~text
PENDING → STOCK_RESERVED → PAID → FULFILLING → DELIVERED
   |             |           |
   v             v           v
REJECTED       CANCELLED   COMPENSATING
~~~

Sơ đồ là một mô hình minh họa, không có nghĩa mọi hệ thống đều phải dùng những enum này. Một hệ thống có thể hỗ trợ trả hàng, thanh toán nhiều lần, giao một phần hoặc hủy sau khi đã đóng gói. Những trường hợp đó cần trạng thái và bất biến phù hợp.

### 3.1. Trạng thái đi kèm bất biến nghiệp vụ

Giả sử Order có các trường:

~~~json
{
  "orderId": "ORD-1001",
  "customerId": "CUS-17",
  "status": "PAID",
  "totalAmount": 500000,
  "currency": "VND",
  "paymentId": "PAY-9001",
  "version": 4
}
~~~

Một số bất biến mẫu:

- Đơn chưa có xác nhận thanh toán hợp lệ không được chuyển tùy tiện sang PAID.
- Một callback giao hàng không được đưa đơn từ DELIVERED quay ngược về FULFILLING.
- Hủy đơn có thể phải chịu giới hạn nếu hàng đã được bàn giao cho đơn vị vận chuyển.
- Hai request thanh toán cho cùng một nghĩa vụ không được tạo hai khoản thu ngoài ý muốn.
- Giá đã chốt của đơn không tự biến đổi chỉ vì bảng giá sản phẩm thay đổi sau đó.

Các bất biến phải được thực thi ở nơi **sở hữu mô hình nghiệp vụ**, không phụ thuộc vào trạng thái đăng nhập hoặc giao diện của khách tại thời điểm callback đến.

### 3.2. Trạng thái và lịch sử không giống nhau

Trường status=PAID cho biết **tình trạng hiện tại**. Để giải thích tại sao và lúc nào trở thành PAID, hệ thống có thể cần lịch sử thay đổi:

~~~text
10:00:00 OrderPlaced(orderId=ORD-1001)
10:00:01 StockReserved(reservationId=RES-7)
10:00:03 PaymentSucceeded(paymentId=PAY-9001)
10:00:04 OrderStatusChanged(PENDING/RESERVED -> PAID)
~~~

Lịch sử có thể được lưu dưới dạng audit records, domain events hoặc event log theo yêu cầu. **Không mặc định** rằng hễ sử dụng sự kiện thì đã áp dụng Event Sourcing. Với kiểu lưu state hiện tại, database lưu entity và một bảng audit riêng cũng có thể đáp ứng nhu cầu truy vết. Event Sourcing là lựa chọn sâu hơn, khi chuỗi event được thiết kế làm nguồn để dựng lại trạng thái.

### 3.3. Nguồn sự thật thuộc về Bounded Context

Trong hệ thống tách dịch vụ:

- Ordering sở hữu trạng thái đơn và điều kiện chuyển trạng thái của đơn.
- Inventory sở hữu tồn kho và reservation.
- Payments sở hữu payment attempt, charge, refund và đối soát.
- Shipping sở hữu shipment và tình trạng vận chuyển.
- Identity sở hữu tài khoản, chính sách xác thực và phiên đăng nhập nếu dùng server-side session.

Ordering có thể lưu **paymentStatus** như một bản tóm tắt nhận từ Payments, nhưng không thay thế được bản ghi tài chính có thẩm quyền ở Payments. Nếu một payment đã thành công nhưng event đến muộn, Ordering có thể đang hiển thị PENDING trong một thời gian ngắn. Đây là bài toán nhất quán giữa ngữ cảnh, cần thiết kế rõ chứ không được giải quyết bằng cách chia sẻ bảng database không kiểm soát.

## 4. Trạng thái phiên làm việc: thông tin về tương tác và xác thực

**Session state** ghi nhận bối cảnh của một chuỗi tương tác với người dùng hoặc client. Trên website truyền thống, session thường dùng để biết request nào thuộc cùng trình duyệt và người dùng đã xác thực đến đâu.

Một phiên có thể chứa:

- Một định danh session khó đoán và được cấp an toàn.
- Tham chiếu đến userId/principal đã xác thực.
- Thời điểm tạo, truy cập cuối, hết hạn và mức xác thực hiện tại.
- Thông tin cần cho quy trình đa bước ngắn hạn (nếu không phù hợp lưu ở business service).
- Một số metadata bảo mật như thời điểm xác thực lại hoặc chính sách thiết bị.

Session **không nên là nơi lưu duy nhất** thông tin kiểu “đơn đã thanh toán”, “khách sở hữu sản phẩm nào” hoặc “số dư được chấp nhận”. Những sự thật này phải tồn tại độc lập với việc phiên đăng nhập còn hiệu lực hay không.

### 4.1. Session khác tài khoản người dùng

Một tài khoản có thể tạo **nhiều phiên** trên điện thoại, laptop và trình duyệt khác nhau. Logout ở một thiết bị có thể kết thúc chỉ phiên đó; “đăng xuất tất cả thiết bị” yêu cầu chính sách thu hồi rộng hơn.

~~~text
Customer CUS-17
  ├── Session S-01: Chrome laptop, còn hiệu lực
  ├── Session S-02: điện thoại, còn hiệu lực
  └── Session S-03: trình duyệt cũ, đã hết hạn
~~~

Cả ba phiên có thể truy cập cùng Order ORD-1001 **nếu** người dùng đã xác thực và được cấp quyền. Order không thuộc về Session S-01; Order gắn với danh tính và quan hệ nghiệp vụ Customer CUS-17.

### 4.2. Session khác cookie

**Cookie** là cơ chế lưu/truyền dữ liệu ở trình duyệt. Cookie thường chỉ chứa **session identifier** hoặc một credential/token phù hợp. **Session record** có thể được giữ ở server hoặc ở dạng thông tin đã ký/mã hóa theo thiết kế.

Cookie có thể hết hạn hoặc bị xóa; việc đó không tự xóa dữ liệu nghiệp vụ. Một session cũng có thể được duy trì không dùng cookie, ví dụ client gọi API với bearer token. Nhưng khi dùng token, yêu cầu bảo mật và thu hồi quyền truy cập vẫn phải được thiết kế.

### 4.3. Đừng biến session thành “database mini”

Một lỗi thường gặp là đặt toàn bộ giỏ hàng, đơn đang xử lý, địa chỉ, giá chốt và payment result vào session. Khi phiên hết hạn, dữ liệu nghiệp vụ bị mất hoặc không thể hoàn tất bằng callback bên ngoài.

Hãy đặt câu hỏi: **Nếu khách logout ngay bây giờ, dữ liệu này có còn phải tồn tại không?** Nếu có, nhiều khả năng dữ liệu cần được đưa vào nguồn trạng thái nghiệp vụ bền vững hoặc kho draft có chính sách rõ.

## 5. Luồng minh họa: khách đăng nhập, đặt hàng và quay lại sau đó

Giả sử có ba instance Order Service và một hệ thống quản lý phiên được chia sẻ.

~~~mermaid
flowchart TB
    B[Browser khách hàng] --> G[Gateway / Load Balancer]
    G --> I[Identity / Auth]
    G --> A[Order instance A]
    G --> C[Order instance B]
    G --> D[Order instance C]
    I --> SS[(Session Store / Identity State)]
    A --> DB[(Order Database)]
    C --> DB
    D --> DB
    A --> P[Payment Service]
    C --> P
    D --> P
~~~

Sơ đồ trên là mô hình khái niệm; request không bắt buộc đi qua mọi nhánh. Session Store nằm ngoài các instance Order; Order Database là nơi trạng thái nghiệp vụ của Ordering được lưu theo ranh giới dịch vụ.

Một hành trình có thể diễn ra như sau:

1. Khách đăng nhập. Identity xác thực và tạo/ghi nhận phiên S-01 hoặc phát token truy cập theo thiết kế.
2. Trình duyệt gọi POST /orders. Gateway kiểm tra credential; Order instance A xử lý và tạo ORD-1001 trong Order Database.
3. Khách gọi GET /orders/ORD-1001. Request lần này được đưa đến Order instance C. C đọc cùng nguồn dữ liệu nghiệp vụ nên vẫn trả đúng đơn.
4. Khách đóng trình duyệt; session S-01 hết hạn sau một thời gian.
5. Payment Service nhận webhook thanh toán và xác minh giao dịch, tiếp tục quy trình nghiệp vụ mà **không cần phiên đăng nhập của khách còn sống**.
6. Hôm sau khách đăng nhập qua phiên S-02, được phân quyền đọc ORD-1001 dựa trên customerId và chính sách authorization.
7. Nếu Order instance A restart, các dữ liệu nghiệp vụ đã commit vẫn phải sẵn sàng qua những instance khác và kho dữ liệu bền vững.

Không có bước nào yêu cầu “session S-01 phải chứa Order ORD-1001”. Session và Order dùng **hai cơ chế vòng đời khác nhau**.

## 6. Stateless application không có nghĩa “không lưu trạng thái”

Trong Microservices thường có lời khuyên **stateless application instances**. Ý đúng là request cần được xử lý mà không yêu cầu một client phải quay lại **đúng cùng một instance** mới đọc được trạng thái quan trọng.

Hãy phân biệt:

- **Stateless instance:** không giữ trạng thái lâu dài chỉ trong RAM của một process mà request sau phải dựa vào; dữ liệu cần tồn tại xuyên instance được lưu ở backend phù hợp.
- **Stateful domain:** vẫn có đơn, thanh toán, shipment, reservation cần lưu bền vững.
- **Stateful session service:** có thể lưu session ở Redis hoặc database và truy xuất bằng sessionId từ bất kỳ instance được phép nào.
- **Token-based authentication:** server có thể xác minh token mà không đọc một session record cho mỗi request, nhưng vẫn cần thiết kế lưu và thu hồi quyền truy cập, refresh token, account status và các chính sách liên quan.

Một Order Service có ba instance A/B/C nhưng cùng sử dụng Order Database là ví dụ các **instance xử lý stateless** trong khi **dịch vụ vẫn có business state**.

### Ví dụ không phù hợp khi scale-out

~~~java
// Không dùng Map trong JVM làm nguồn dữ liệu nghiệp vụ của nhiều replica.
private static final Map<String, Order> orders = new ConcurrentHashMap<>();

public Order create(Order order) {
    orders.put(order.id(), order);
    return order;
}
~~~

Nếu request đầu vào A còn request thứ hai vào B, B có Map riêng và có thể trả 404. ConcurrentHashMap chỉ bảo vệ truy cập đồng thời **trong cùng JVM**.

Tương tự, đặt session vào một static Map trong Order Service khiến một user có thể “đăng nhập lúc được, lúc mất” khi load balancer chuyển request sang instance khác.

### Mô hình đúng cấp trách nhiệm

~~~text
HTTP request + credential
        |
        v
  [Instance bất kỳ]
        |
        +--> kiểm tra danh tính / session / token theo chính sách
        |
        +--> đọc/ghi business state qua domain repository
        |
        +--> trả về dữ liệu tương ứng quyền truy cập
~~~

Một cache local vẫn hữu ích nếu **dữ liệu có thể tái tạo** và có chiến lược invalidation/TTL phù hợp. Không nhầm cache với nguồn sự thật.

## 7. Chọn nơi lưu business state

Những câu hỏi quyết định nơi lưu là: dữ liệu phải tồn tại bao lâu, ai sở hữu, có cần transaction/constraint không, có cần query/audit không, và khi ghi đồng thời thì ai phân xử?

### 7.1. Database giao dịch của dịch vụ

Đối tượng nghiệp vụ cần tính nhất quán cục bộ thường nằm trong database thuộc quyền sở hữu của context đó: Order, Payment, Stock Reservation. Database có thể là quan hệ hoặc NoSQL, tùy mô hình truy vấn và bất biến; quan trọng là **các thao tác bảo vệ đúng tính toàn vẹn**.

Ví dụ bản ghi Order:

~~~sql
CREATE TABLE orders (
    order_id VARCHAR(64) PRIMARY KEY,
    customer_id VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL,
    total_amount BIGINT NOT NULL,
    currency CHAR(3) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
~~~

Đây là schema minh họa. Hệ thống thật có thể bổ sung dòng hàng, bảng trạng thái, unique constraints, quan hệ, audit và chính sách xử lý tiền.

### 7.2. Quy tắc và giao dịch cục bộ

Ví dụ chuyển từ PENDING sang ACCEPTED chỉ khi trạng thái hiện tại hợp lệ:

~~~sql
UPDATE orders
SET status = 'ACCEPTED',
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE order_id = 'ORD-1001'
  AND status = 'PENDING'
  AND version = 3;
~~~

Nếu ảnh hưởng **0 dòng**, có thể trạng thái/version đã đổi hoặc đơn không tồn tại. Handler cần đọc lại và trả kết quả phù hợp; không mặc định “database lỗi”. Kiểu cập nhật có điều kiện hoặc optimistic locking giúp bảo vệ invariant khi hai instance cùng thao tác.

Một mẫu ở tầng Java/Spring minh họa ý tưởng:

~~~java
@Entity
class OrderEntity {
    @Id
    String id;

    @Version
    long version;

    @Enumerated(EnumType.STRING)
    OrderStatus status;

    // other domain fields...
}

@Service
class OrderApplicationService {
    private final OrderRepository orders;

    OrderApplicationService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public void accept(String orderId) {
        OrderEntity order = orders.findById(orderId)
            .orElseThrow(() -> new OrderNotFoundException(orderId));

        if (order.status != OrderStatus.PENDING) {
            throw new InvalidOrderTransitionException(order.status);
        }

        order.status = OrderStatus.ACCEPTED;
        // JPA sẽ kiểm tra @Version tại thời điểm flush/update.
    }
}
~~~

Các class, enum và repository ngoài đoạn trích phải được định nghĩa trong ứng dụng; đây là ví dụ giải thích chỗ thực thi điều kiện, không phải dự án hoàn chỉnh. Với optimistic lock conflict, tầng ứng dụng cần quyết định trả HTTP 409, đọc lại, hoặc retry có giới hạn nếu thao tác được xác định an toàn.

### 7.3. Redis/cache không mặc nhiên là durable database

Redis có thể phục vụ cache, rate-limit state, session hoặc dữ liệu nghiệp vụ trong một số thiết kế có persistence và HA được chọn kỹ. Nhưng **TTL, eviction, replication, durability và chính sách backup** phải phù hợp hậu quả mất dữ liệu. Không đưa bản ghi thanh toán có giá trị pháp lý vào một key cache có TTL ngắn chỉ vì truy xuất nhanh.

### 7.4. Event log / Event Sourcing

Một số context có thể lấy **event history** làm nguồn sự thật và dựng trạng thái hiện tại từ các event. Cách này hữu ích khi cần truy vết biến đổi phức tạp, nhưng có thêm chi phí version event, migration, replay, snapshots, kiểm soát side effects và projection. Không nên chọn chỉ vì hệ thống đang dùng Kafka hoặc RabbitMQ.

## 8. Thiết kế vòng đời business state như state machine

Một model domain tốt không chỉ giữ enum; nó xác định **điều kiện chuyển trạng thái**, ai được phép kích hoạt và xử lý event lặp/đến trễ ra sao.

Ví dụ bảng chuyển trạng thái của đơn (mang tính minh họa):

| Trạng thái hiện tại | Tín hiệu/command | Điều kiện | Trạng thái kế tiếp |
| --- | --- | --- | --- |
| PENDING | StockReserved | Reservation hợp lệ của đơn | STOCK_RESERVED |
| PENDING | StockRejected | Không đủ hàng | REJECTED |
| STOCK_RESERVED | PaymentSucceeded | PaymentId và amount phù hợp | PAID |
| STOCK_RESERVED | PaymentFailed | Từ chối cuối cùng, cần giải phóng reservation | COMPENSATING |
| PAID | ShipmentCreated | Shipment hợp lệ | FULFILLING |
| FULFILLING | ShipmentDelivered | Bằng chứng giao nhận hợp lệ | DELIVERED |
| PAID | ShippingFailed | Chính sách yêu cầu hoàn tiền/hủy | COMPENSATING |
| COMPENSATING | RefundSucceeded + StockReleased | Các nghĩa vụ bù hoàn thành | CANCELLED |

**Một event không tự động hợp lệ trong mọi trạng thái.** Nếu ShipmentCreated đến sau ShipmentDelivered vì thứ tự truyền bị đảo, không đưa đơn quay ngược về FULFILLING. Nếu PaymentSucceeded đến sau khi client timeout, phải đối soát với payment attempt tương ứng trước khi quyết định bước tiếp theo.

Các tính chất quan trọng:

- **Safety:** không cho phép chuyển trạng thái làm sai bất biến.
- **Liveness:** tiến trình không bị kẹt mãi ở trạng thái tạm nếu có cơ chế timeout, retry và xử lý ngoại lệ.
- **Idempotency:** nhận lại cùng lệnh/event không tạo thêm tác động ngoài ý muốn.
- **Auditability:** biết ai/tín hiệu nào gây thay đổi và có bằng chứng nào xác nhận.

State machine có thể được hiện thực bằng điều kiện domain method, command handler và transaction; không nhất thiết phải có framework state machine riêng.

## 9. Giao dịch và nhất quán giữa nhiều Microservices

Giữa Ordering, Inventory, Payments và Shipping có nhiều database riêng. Một transaction trong Order Database **không tự commit hoặc rollback** các thay đổi tại Payment Service hay nhà cung cấp thanh toán bên ngoài.

### 9.1. Giao dịch cục bộ

Trong một service, thay đổi entity Order và ghi một Outbox event có thể cùng thuộc **một transaction cục bộ**.

~~~text
Order DB transaction:
    UPDATE order status
    INSERT outbox event OrderStatusChanged
COMMIT

Outbox publisher:
    đọc event chưa phát
    gửi tới broker
    ghi nhận checkpoint/đánh dấu đã phát
~~~

Nếu process chết sau commit nhưng trước khi gửi message, publisher có thể phát lại từ outbox. Nếu phát message xong rồi chết trước khi đánh dấu, message có thể được gửi trùng. Vì vậy consumer cần idempotency; không dựa vào “exactly once toàn hệ thống”.

### 9.2. Saga cho quy trình nhiều bước

Một quy trình checkout có thể cần:

~~~mermaid
sequenceDiagram
    autonumber
    participant O as Ordering / Saga
    participant I as Inventory
    participant P as Payments
    participant S as Shipping

    O->>I: ReserveStock
    I-->>O: StockReserved
    O->>P: ChargePayment
    P-->>O: PaymentSucceeded
    O->>S: CreateShipment
    S-->>O: ShipmentCreated
~~~

Nếu Payments thất bại sau khi Inventory giữ hàng, Saga yêu cầu ReleaseStock. Nếu Payments đã xác nhận thu tiền nhưng Shipping không thể tạo shipment và chính sách yêu cầu hủy, Saga yêu cầu RefundPayment rồi theo dõi xác nhận bù.

**Quan trọng:** Saga là business workflow có trạng thái riêng; không nên lưu Saga progress chỉ trong session của khách. Khách có thể logout, app có thể restart, webhook có thể tới muộn; Saga vẫn phải tiến hành an toàn.

### 9.3. Eventual consistency

Order có thể hiển thị PENDING trong một khoảng thời gian trong khi Payment Service đã xác nhận thanh toán. Đây là trạng thái tạm khi các ngữ cảnh trao đổi bất đồng bộ. Cần quy định độ trễ chấp nhận và cơ chế đối soát:

- Payment là nguồn sự thật giao dịch tài chính.
- Ordering lưu projection/trạng thái tổng hợp phục vụ người dùng.
- Event có eventId, correlationId, orderId và version/sequence phù hợp.
- Consumer xử lý trùng và tránh lùi trạng thái.
- Monitoring cảnh báo khi một bước chờ quá lâu.
- Reconciliation xác minh hệ thống nguồn trước khi kết luận thất bại hay thu tiền lại.

Nên tránh trả “Thất bại” chỉ vì UI đợi quá thời hạn. Với giao dịch bên ngoài, **timeout = chưa biết kết quả** cho đến khi đã xác minh.

## 10. Idempotency là yêu cầu cốt lõi cho business state

Khi một request mất phản hồi, client hoặc gateway có thể retry, và request sau có thể đi vào instance khác. Nếu chỉ kiểm tra biến RAM cục bộ, cả hai request có thể tạo hai đơn hoặc hai lần thu tiền.

Ví dụ client tạo đơn:

~~~http
POST /orders HTTP/1.1
Idempotency-Key: checkout-7f21
Content-Type: application/json

{
  "items": [
    { "sku": "BOOK-01", "quantity": 2 }
  ],
  "shippingAddressId": "ADDR-08"
}
~~~

Một thiết kế idempotency hợp lý:

1. Xác định **scope** của key (ví dụ userId + operation + idempotencyKey).
2. Gắn key với **fingerprint của payload** và trạng thái xử lý.
3. Dùng unique constraint/transaction để hai instance không cùng tạo hai thao tác cho một key.
4. Khi retry cùng key + cùng payload, trả kết quả đã lưu hoặc trạng thái đang xử lý của **cùng một thao tác**.
5. Khi cùng key nhưng payload khác, trả xung đột thích hợp, không âm thầm dùng lại kết quả không liên quan.
6. Định nghĩa thời gian lưu, cách xử lý key hết hạn, và khả năng kiểm tra trạng thái bằng orderId.
7. Với payment, còn phải bảo đảm idempotency và reconciliation tại cổng thanh toán, vì một HTTP timeout không chứng minh khoản thu chưa xảy ra.

Idempotency là **trạng thái của thao tác nghiệp vụ**. Không lưu bằng một session attribute cục bộ ở instance A, vì request retry có thể tới instance B hoặc xảy ra sau khi phiên hết hạn.

### Minh họa race condition

~~~text
A nhận POST /orders với key K
B nhận lại POST /orders với key K

Sai:
A: SELECT không thấy K
B: SELECT không thấy K
A: INSERT Order-1
B: INSERT Order-2

Đúng về ý tưởng:
unique constraint (scope, key)
+ transaction / atomic reservation
+ quy tắc trả kết quả của thao tác K
~~~

Không nhất thiết chỉ có một kỹ thuật SQL; có thể dùng cơ chế atomic tương đương. Điểm quyết định là **bất biến chống trùng được bảo vệ ở tài nguyên dùng chung**, chứ không chỉ ở thread hiện tại.

## 11. Quản lý session khi có nhiều instance

Một hệ thống chạy ba instance API A/B/C không thể mặc định request thứ hai vẫn vào A. Session phải được thiết kế phù hợp với routing.

### 11.1. Session trong RAM của từng instance

~~~text
Browser --cookie S-01--> Load Balancer
                         ├── Instance A: biết S-01
                         ├── Instance B: không biết S-01
                         └── Instance C: không biết S-01
~~~

Tình huống này gây đăng nhập “chập chờn” khi client bị chuyển backend. Nếu dùng session server-side, cần cơ chế để tất cả instance được phép tra cứu đúng session và thống nhất thời hạn, trạng thái thu hồi.

### 11.2. Session store dùng chung

~~~mermaid
flowchart TB
    U[Browser / mobile client] --> G[Gateway]
    G --> A[App instance A]
    G --> B[App instance B]
    G --> C[App instance C]
    A --> R[(Shared Session Store)]
    B --> R
    C --> R
    A --> D[(Business DB)]
    B --> D
    C --> D
~~~

Client gửi session identifier; instance xác minh và đọc session từ **shared store**. Một request mới tới B vẫn có thể nhận biết cùng user đã được xác thực.

Shared session store có thể dùng Redis hoặc database với cấu hình TTL, độ sẵn sàng và bảo mật phù hợp. Dữ liệu session chỉ nên chứa thông tin cần thiết, không phình to với entity nghiệp vụ.

**Các vấn đề cần định nghĩa trước:**

- Khi session hết hạn, request nhận 401 hay được chuyển đến login?
- Sliding expiration có được cập nhật khi client hoạt động?
- Logout thu hồi đúng session nào và trong bao lâu?
- Session có bị mất nếu Redis failover/eviction không?
- Những trường nào cần serialize, và thay đổi schema session giữa rolling deployment được xử lý thế nào?
- Có chính sách giới hạn số phiên đồng thời hay phát hiện thiết bị bất thường không?

### 11.3. Sticky session / session affinity

Load balancer có thể cố giữ một client vào cùng instance. Điều này đôi khi giảm số lần truy xuất session store hoặc hỗ trợ ứng dụng legacy, nhưng **không thể là cơ chế duy nhất bảo đảm dữ liệu đúng**:

- Instance có thể chết hoặc bị scale in.
- Routing có thể đổi sau deploy, mất cookie affinity hoặc thay mạng.
- Instance nóng và instance rảnh có thể mất cân bằng.
- Callback từ payment provider không mang session của browser.

Dùng affinity khi có lý do cụ thể, đồng thời xác định rõ hành vi failover. Không xem sticky session là lý do để lưu order/payment chỉ trong RAM.

## 12. Server-side session và token-based authentication

Hai mô hình này có ưu và nhược điểm khác nhau. Cả hai có thể kết hợp với kiến trúc nhiều Microservices.

| Tiêu chí | Server-side session | Token-based access (ví dụ JWT được ký) |
| --- | --- | --- |
| Client giữ gì? | Thường cookie chứa session ID | Access token, có thể gửi theo Authorization hoặc cookie theo thiết kế |
| Server tìm trạng thái xác thực | Truy xuất session record hoặc cache | Xác minh chữ ký/claim và các kiểm tra bổ sung |
| Thu hồi tức thời | Có thể xóa/vô hiệu session trong shared store | Token tự chứa thường cần thời hạn ngắn hoặc cơ chế revocation/introspection |
| Mở rộng nhiều instance | Cần session store/shared validation nhất quán | Các instance dùng cùng chính sách xác minh key/issuer/audience |
| Mất session store | Có thể khiến request xác thực lỗi | Access token còn hiệu lực có thể vẫn xác minh được nếu không cần gọi store |
| Dữ liệu nhạy cảm ở phía client | Chỉ để identifier khó đoán | Token có thể chứa claims người dùng đọc được nếu là JWT thường |
| Bảo mật đi kèm | Cookie flags, CSRF, fixation, TTL | Signature, audience, issuer, expiry, rotation, storage/XSS/CSRF tùy cách truyền |

**Không đánh đồng JWT với “an toàn hơn” hoặc “stateless tuyệt đối”.** Một JWT được ký thường **không được mã hóa**: payload có thể được đọc khi ai đó có token. Không đưa thông tin nhạy cảm không cần thiết vào claim. Phải xác minh thuật toán cho phép, chữ ký, issuer, audience, expiry, not-before và chính sách key rotation. Nếu yêu cầu logout hiệu lực tức thời, hệ thống phải định nghĩa cơ chế thu hồi/phân quyền thời gian thực thích hợp.

### 12.1. Cookie session: những cấu hình quan trọng

Ví dụ header minh họa:

~~~http
Set-Cookie: SESSION=opaque-random-id; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

- **Secure:** cookie chỉ được gửi qua kết nối an toàn theo quy tắc trình duyệt.
- **HttpOnly:** script client không thể đọc cookie này trực tiếp, giảm rủi ro lấy token qua một số kiểu XSS (nhưng không thay cho việc chống XSS).
- **SameSite:** hạn chế một số tình huống gửi cookie xuyên site; chọn Lax/Strict/None phù hợp luồng login và tích hợp. SameSite=None thường phải đi cùng Secure.
- **Path/Domain/Expires/Max-Age:** giới hạn phạm vi và thời gian sống đúng nhu cầu.

Nếu ứng dụng dùng cookie tự động gửi cho các request thay đổi dữ liệu, cần phân tích **CSRF** và áp dụng biện pháp bảo vệ thích hợp; SameSite một mình không phải giải pháp toàn diện trong mọi tình huống.

### 12.2. Token: phân biệt access token và refresh token

Access token thường có thời gian sống tương đối ngắn và dùng gọi API. Refresh token được dùng để lấy access token mới theo chính sách và thường cần lưu/thu hồi/rotate an toàn. Logout ở client không nhất thiết làm access token tự chứa ngừng hợp lệ ngay lập tức.

Với một hệ thống cần “đăng xuất tất cả thiết bị ngay” hoặc “khóa tài khoản có hiệu lực tức thì”, hãy xác định cách enforcement tại API: kiểm tra phiên/token server-side, denylist theo chính sách, version của credential hoặc introspection. Mỗi lựa chọn ảnh hưởng latency, availability và độ tươi của thông tin.

### 12.3. Session authentication khác authorization nghiệp vụ

**Authentication** trả lời “ai đang gửi request?”. **Authorization** trả lời “người này được làm gì với tài nguyên này?”.

Một user đăng nhập hợp lệ không đương nhiên được xem ORD-1001. Order Service phải kiểm tra quyền theo owner/tenant/role/chính sách nghiệp vụ, ví dụ customerId của đơn hoặc quyền nhân viên chăm sóc khách hàng được cấp hợp lệ. Không nhận customerId do client tự nhập như bằng chứng quyền.

## 13. Spring Boot: ví dụ tổ chức trách nhiệm

Trong ứng dụng Java/Spring Boot, cách tổ chức thường có các lớp:

~~~text
Security filter / authentication adapter
    -> xác minh credential hoặc session
    -> tạo authenticated principal
    -> Controller nhận request
    -> Application Service kiểm tra authorization nghiệp vụ
    -> Domain Model kiểm tra invariant
    -> Repository lưu trạng thái nghiệp vụ
~~~

Với app dùng server-side session, cơ chế như **Spring Session** có thể thay local HttpSession store bằng nguồn dùng chung khi được cấu hình đúng. Với API dùng bearer token, Spring Security Resource Server có thể xác minh token theo chính sách. Đây là hai hướng triển khai; không nên bật đồng thời nhiều cơ chế mà chưa thiết kế rõ route nào sử dụng cái gì.

### 13.1. Không đưa HttpSession vào domain

Ví dụ không tốt:

~~~java
@PostMapping("/orders")
public Order create(HttpSession session) {
    Cart cart = (Cart) session.getAttribute("cart");
    Order order = new Order(cart);
    session.setAttribute("lastOrder", order);
    return order; // Chưa có nguồn lưu business state bền vững.
}
~~~

Nếu chỉ giữ Order trong session, callback thanh toán hoặc một phiên khác có thể không truy cập được đối tượng. HTTP session là một cơ chế giao tiếp/xác thực, không phải aggregate repository.

### 13.2. Lớp API xác định identity, domain xử lý nghiệp vụ

Mẫu đơn giản:

~~~java
@RestController
@RequestMapping("/orders")
class OrderController {
    private final OrderApplicationService orders;

    OrderController(OrderApplicationService orders) {
        this.orders = orders;
    }

    @PostMapping
    ResponseEntity<OrderResponse> create(
        @AuthenticationPrincipal AuthenticatedUser user,
        @RequestHeader("Idempotency-Key") String key,
        @RequestBody CreateOrderRequest request
    ) {
        OrderResponse result = orders.create(user.userId(), key, request);
        return ResponseEntity.status(201).body(result);
    }

    @GetMapping("/{orderId}")
    OrderResponse get(
        @AuthenticationPrincipal AuthenticatedUser user,
        @PathVariable String orderId
    ) {
        return orders.getAuthorized(user.userId(), orderId);
    }
}
~~~

**AuthenticatedUser, OrderApplicationService, OrderResponse, CreateOrderRequest** là type minh họa cần được định nghĩa. Trong hệ thống thật, cần thêm validation, chuẩn lỗi, quyền theo tenant, trạng thái async và response code thích hợp.

Điểm tách trách nhiệm:

1. Security adapter xác định principal từ session/token hợp lệ.
2. Application Service nhận userId đã xác thực và kiểm tra quyền với Order.
3. Domain Service/Aggregate quyết định chuyển trạng thái nghiệp vụ.
4. Repository ghi/đọc dữ liệu bền vững và bảo vệ giao dịch.
5. Request kế tiếp có thể được xử lý ở instance khác mà không thay đổi kết quả nghiệp vụ.

### 13.3. Ví dụ pseudo-configuration cho shared session

~~~text
Ứng dụng A/B/C:
  - cùng session cookie name và chính sách bảo mật
  - cùng namespace/session store được cấp quyền truy cập
  - cùng cách serialize dữ liệu cần thiết
  - cùng phiên bản tương thích của security/session format

Session store:
  - TTL theo chính sách
  - cấu hình authentication và network protection
  - capacity/eviction/HA phù hợp
  - monitoring và alert

Business DB:
  - aggregate Order và transaction riêng
  - version/unique constraints
  - audit và outbox khi cần
~~~

Không nên copy một file cấu hình demo rồi cho rằng session an toàn/HA đã hoàn tất; điều quan trọng là các **ràng buộc vận hành** ở trên được đáp ứng bởi stack cụ thể.

## 14. Quy trình nhiều bước: nên đặt trạng thái ở đâu?

Một quá trình checkout gồm các bước: chọn địa chỉ, chọn phương thức giao, xác nhận giá, thanh toán. Có nhiều loại dữ liệu:

| Dữ liệu | Nơi lưu phù hợp theo tình huống | Lý do |
| --- | --- | --- |
| Ô nhập form chưa lưu | State của browser/component | Có thể mất khi reload nếu yêu cầu chỉ là tạm |
| Draft checkout cần khôi phục sau đăng nhập | Draft repository hoặc cart context | Cần tồn tại xuyên session, có version/TTL nghiệp vụ |
| Địa chỉ đã lưu của khách | Customer Profile | Là thông tin người dùng có vòng đời riêng |
| Giá báo tạm có thời hạn | Pricing Quote context | Có điều kiện hiệu lực và nguồn xác nhận |
| Giá được chốt khi đặt | Order aggregate/snapshot | Cần audit và giữ nguyên sau thay đổi giá |
| Khóa idempotency cho tạo đơn | Storage chung của operation | Phải chống retry xuyên instance |
| Order đã tạo | Order Database | Nguồn sự thật nghiệp vụ |
| Payment attempt | Payment Database | Nghĩa vụ tài chính và đối soát |
| Tình trạng đăng nhập hiện tại | Auth/session mechanism | Có thể hết hạn/thu hồi độc lập với đơn |
| Loading spinner | UI state | Không phải trạng thái đơn ở server |

Đừng coi mọi thứ có thể hết hạn là session state. Một **quote** hoặc **reservation** có TTL vẫn là đối tượng nghiệp vụ vì cần quy tắc hết hạn, audit và ảnh hưởng đến quyết định domain. Ngược lại, một feature flag trong runtime có thể tồn tại lâu nhưng không phải business state của một Order.

### Ví dụ khách bỏ dở checkout

Nếu doanh nghiệp muốn gửi email nhắc giỏ hàng bỏ dở sau 24 giờ, cần một mô hình cart/draft được phép lưu và xử lý theo chính sách dữ liệu. Không thể dựa vào HttpSession sống đủ 24 giờ và cho rằng mọi browser đều quay lại đúng instance.

Cũng cần cân nhắc quyền riêng tư, đồng ý nhận thông báo và thời hạn lưu; không biến dữ liệu session thành danh sách marketing không có quy tắc rõ.

## 15. Khi trạng thái phiên hết hạn giữa quy trình

Giả sử khách đã bấm thanh toán, trình duyệt bị đóng ngay, rồi callback thành công đến sau 30 giây.

~~~mermaid
sequenceDiagram
    autonumber
    actor C as Customer
    participant O as Ordering
    participant P as Payments
    participant X as Payment Provider

    C->>O: POST /orders với session hợp lệ
    O->>O: Lưu Order=PAYMENT_PENDING
    O->>P: Yêu cầu thanh toán với orderId
    P->>X: Tạo payment attempt
    C--xO: Browser đóng; session hết hạn
    X-->>P: Webhook thanh toán thành công
    P->>P: Verify + lưu PaymentSucceeded
    P-->>O: PaymentSucceeded(orderId, paymentId)
    O->>O: Chuyển Order sang PAID
    Note over O,P: Không cần session browser còn hiệu lực
~~~

Khi callback đến:

- Payment Service xác minh nguồn webhook bằng chữ ký/chứng thực phù hợp.
- Payment lookup bằng provider reference và paymentId/orderId đã lưu.
- Ordering xử lý sự kiện dựa vào trạng thái nghiệp vụ và quy tắc domain.
- Không cần hoặc không được dựa vào cookie session của khách khi xử lý sự kiện server-to-server.
- Nếu client trở lại, client phải xác thực mới trước khi xem đơn.

Một callback thanh toán không phải một request “được người dùng ủy quyền thông qua cookie”. Nó có **mô hình tin cậy giữa hệ thống** khác, cần identity và authorization riêng cho integration.

## 16. Failure modes khi nhầm trạng thái nghiệp vụ và phiên

### 16.1. Logout làm mất đơn

**Triệu chứng:** User logout, login lại thì không xem được đơn vừa tạo.

**Nguyên nhân có thể:** Order chỉ lưu trong session; hoặc query lấy đơn theo sessionId thay vì owner/tenant identity.

**Thiết kế phù hợp:** Order được lưu bền vững, gắn customerId; session chỉ dùng xác thực và lấy principal. Khi login lại, API đọc đơn sau khi kiểm tra quyền.

### 16.2. Request đi vào instance khác làm mất trạng thái đăng nhập

**Triệu chứng:** User đăng nhập ở A rồi request sau đi B và B trả 401.

**Nguyên nhân:** B không có session record; cookie chứa một ID được A lưu cục bộ.

**Thiết kế phù hợp:** shared session store, hoặc mô hình token xác thực hợp lệ tại mọi instance, với chính sách thu hồi được định nghĩa rõ.

### 16.3. Process restart làm mất trạng thái thanh toán

**Triệu chứng:** Khởi động lại Payment Service khiến các payment attempt đang chờ bị quên.

**Nguyên nhân:** chỉ giữ trạng thái attempt trong RAM hoặc queue không bền vững.

**Thiết kế phù hợp:** lưu attempt/correlation/reference vào data store theo yêu cầu durability; xử lý webhook idempotent; có reconciliation.

### 16.4. Hai browser cùng hủy/sửa một đơn

**Triệu chứng:** Tab A hủy, Tab B bấm xác nhận giao và ghi đè trạng thái, làm đơn “sống lại”.

**Nguyên nhân:** update không kiểm tra state/version hợp lệ.

**Thiết kế phù hợp:** domain transition + optimistic locking hoặc điều kiện atomic. Với thao tác xung đột, API trả 409/hiện trạng mới để client quyết định tiếp.

### 16.5. Session store gặp lỗi

**Triệu chứng:** Các API cần xác thực đồng loạt trả 401/503 dù Order Database còn hoạt động.

**Nguyên nhân:** session store là phụ thuộc chung; có nhiều app instance không loại bỏ SPOF nếu store hoặc network liên quan vẫn lỗi.

**Thiết kế phù hợp:** HA, bảo vệ connection, alert, giới hạn retry và hành vi fail-closed với yêu cầu bảo mật. Không tự mở quyền truy cập đơn chỉ vì không đọc được session.

### 16.6. JWT đã phát vẫn còn hiệu lực sau logout

**Triệu chứng:** Client đã logout nhưng token cũ chưa hết hạn vẫn gọi được API.

**Nguyên nhân:** xác minh JWT self-contained mà không có cơ chế thu hồi tương ứng.

**Thiết kế phù hợp:** access token ngắn hạn, refresh token rotation/revocation và cơ chế enforcement theo mức rủi ro. Xác định rõ logout trên thiết bị, logout toàn bộ và khóa tài khoản cần hiệu lực trong bao lâu.

### 16.7. Cache stale tạo ra quyết định sai

**Triệu chứng:** Order A chấp nhận hủy dựa trên cache cũ còn Order B đã chuyển đơn sang FULFILLING.

**Nguyên nhân:** dùng cache làm căn cứ cuối cho invariant.

**Thiết kế phù hợp:** dùng điều kiện cập nhật tại nguồn dữ liệu hoặc cơ chế nhất quán phù hợp khi quyết định nghiệp vụ; cache chỉ là lớp đọc có quy tắc invalidation và chấp nhận stale rõ.

## 17. Bảo mật và quyền riêng tư cho session

Session và token thường là **credentials**. Nếu bị lộ, kẻ khác có thể hành động như người dùng trong phạm vi được cấp. Vì vậy cần các kiểm soát bảo mật phù hợp với mối đe dọa thực tế.

### 17.1. Session identifier

- Tạo bằng nguồn ngẫu nhiên mật mã, đủ độ khó đoán.
- Không dùng userId, email, orderId hoặc chuỗi tuần tự làm session identifier.
- Rotate/regenerate session ID sau thay đổi mức xác thực quan trọng như login để phòng session fixation.
- Có TTL và chính sách idle timeout/absolute timeout phù hợp.
- Vô hiệu session khi logout hoặc khi xác thực lại theo chính sách.
- Chỉ cho phép truy cập session store qua mạng và credential được phân quyền.

### 17.2. Cookie và browser

- Bật Secure, HttpOnly, SameSite phù hợp và HTTPS.
- Cân nhắc CSRF với cookie tự động gắn vào request; dùng CSRF token hoặc biện pháp tương đương theo framework/luồng.
- Chống XSS và tránh đưa token nhạy cảm vào URL, log hoặc client-side telemetry.
- Với các ứng dụng cross-origin, hiểu rõ CORS và cookie credential; CORS không thay thế authorization.

### 17.3. Token và service-to-service identity

- Xác minh chữ ký, thuật toán cho phép, issuer, audience, thời hạn và key rotation.
- Không tin vào claim chỉ vì client gửi một JWT trông đúng định dạng.
- Truyền token qua HTTPS, giảm scope và lifetime, dùng secret management.
- Tách danh tính service-to-service khỏi danh tính phiên browser; webhook và message consumer cần cơ chế xác thực riêng.
- Không đưa số thẻ, mật khẩu, refresh token hay thông tin nhạy cảm vào event nghiệp vụ.

### 17.4. Authorization phải kiểm tra lại ở domain boundary

Ví dụ GET /orders/ORD-1001 cần xác minh user có quyền xem đơn. Một Session S-02 đã xác thực hợp lệ không phải bằng chứng sở hữu ORD-1001 nếu order.customerId khác. Một nhân viên có thể có quyền quản lý theo tenant/role; đó là chính sách riêng cần được áp dụng cụ thể.

## 18. Tính nhất quán khi nhiều instance cập nhật business state

Khi nhiều instance xử lý song song, **một nguồn dữ liệu dùng chung** mới chỉ giải quyết phần nhìn thấy dữ liệu. Tính đúng đắn còn cần concurrency control.

### 18.1. Lost update

Giả sử Order version=3, trạng thái PENDING. A và B cùng đọc:

~~~text
A đọc Order v3 PENDING
B đọc Order v3 PENDING
A chấp nhận đơn -> v4 ACCEPTED
B hủy đơn -> ghi đè v4 CANCELLED theo dữ liệu cũ
~~~

Nếu cả hai update không có điều kiện, kết quả có thể bỏ mất quyết định đã commit trước. Dùng @Version/optimistic locking hoặc update có điều kiện để một bên phát hiện conflict rồi quyết định theo trạng thái mới.

### 18.2. Double spending hoặc overselling

Hai request đồng thời muốn giữ chiếc hàng cuối cùng. Đọc available=1 ở hai instance không đủ; Inventory phải thực hiện reservation **nguyên tử**, chẳng hạn cập nhật có điều kiện available >= quantity và kiểm soát bản ghi reservation.

Không dùng Java synchronized trên Order A để bảo vệ hàng nằm ở Inventory B. Khóa JVM không liên thông giữa nhiều instance.

### 18.3. Sự kiện đến trùng và sai thứ tự

Một consumer có thể nhận PaymentSucceeded hai lần hoặc nhận trạng thái “ShipmentCreated” sau “ShipmentDelivered”. Cần:

- eventId / idempotency key để chống thực hiện tác động trùng;
- trạng thái hiện hành và điều kiện chuyển hợp lệ;
- version/sequence khi thứ tự theo từng aggregate có ý nghĩa;
- quy tắc xử lý event lạ hoặc không thể áp dụng, có audit;
- cách retry/đưa vào hàng xử lý ngoại lệ thay vì âm thầm bỏ qua lỗi quan trọng.

**Thứ tự đến broker** không luôn là thứ tự sự kiện nghiệp vụ xảy ra trên toàn hệ thống. Không dựa vào một timestamp từ máy bất kỳ để quyết định mọi quan hệ nhân quả.

### 18.4. Trạng thái tổng hợp từ nhiều nguồn

Nếu UI hiển thị:

~~~json
{
  "orderId": "ORD-1001",
  "orderStatus": "FULFILLING",
  "paymentStatus": "SUCCEEDED",
  "shipmentStatus": "IN_TRANSIT",
  "lastSyncedAt": "2026-11-11T10:00:00Z"
}
~~~

Đây có thể là một read model/projection. Trường paymentStatus có nguồn gốc từ Payments, shipmentStatus từ Shipping. Nếu một event tới trễ, projection có thể chưa cập nhật ngay. Tài liệu API cần nói rõ mức độ tươi dữ liệu và hành vi khi không đồng bộ.

## 19. Observability: theo dõi trạng thái ở đúng cấp

Khi điều tra lỗi, hãy tách câu hỏi “đơn đang ở bước nào?” khỏi “phiên browser còn hiệu lực không?” và “instance nào bị lỗi?”.

| Tầng | Thông tin nên quan sát | Tình huống cần phát hiện |
| --- | --- | --- |
| Business | orderId, status, version, Saga step, payment reference | Đơn kẹt PENDING/COMPENSATING |
| Session/Auth | session creation/revocation, active sessions, auth failures | Đăng nhập thất bại hàng loạt, session store lỗi |
| Request | requestId, traceId, authenticated principal đã ẩn thông tin nhạy cảm | Request trả 401/409/500 ở đâu |
| Instance | instanceId, CPU, memory, readiness, restart, connection pools | Lỗi chỉ xảy ra ở một replica |
| Integration | broker lag, dead-letter queue, webhook age, retry count | Event đến trễ, đối soát chưa xong |
| Storage | DB latency, locks, conflicts, Redis eviction/TTL | Mất phiên, race condition, nghẽn dữ liệu |

Ví dụ chuỗi log có thể là:

~~~text
service=gateway requestId=req-1 userRef=U-17 auth=success instance=g1
service=order requestId=req-1 orderId=ORD-1001 state=PENDING instance=order-a
service=payments correlationId=checkout-7f21 paymentId=PAY-9001 result=SUCCEEDED
service=order correlationId=checkout-7f21 orderId=ORD-1001 state=PAID instance=order-c
~~~

Đừng ghi session ID thô, JWT, authorization header, mật khẩu hoặc thông tin thanh toán nhạy cảm vào log. Có thể dùng một **session reference đã hash/ẩn danh phù hợp** cho hoạt động hỗ trợ; việc xử lý thông tin nhận diện vẫn phải theo chính sách dữ liệu.

Các cảnh báo hữu ích:

- Số đơn PAYMENT_PENDING vượt thời hạn.
- Refund đã yêu cầu nhưng quá lâu chưa được xác nhận.
- Tỷ lệ optimistic lock conflict tăng đột biến.
- Tỷ lệ 401 tăng đồng thời với lỗi session store.
- Một instance có latency cao hoặc restart nhiều lần.
- Broker consumer lag tăng làm projection chậm cập nhật.

## 20. Chọn phương án thiết kế theo yêu cầu

Không có một phương án lưu trạng thái tốt nhất cho tất cả. Hãy đưa ra quyết định từ yêu cầu.

### Bài toán A — Website thương mại điện tử có login truyền thống

Ứng dụng browser sử dụng cookie và server-side session. Khi scale nhiều replica, dùng shared session store, session ID an toàn, TTL và CSRF protection phù hợp. Order vẫn nằm trong Order Database. Logout chỉ tác động tới phiên, không hủy đơn.

### Bài toán B — Mobile app gọi API qua token

Client gửi access token; mỗi API instance xác minh token theo cùng cấu hình trust. Refresh token có vòng đời riêng; yêu cầu thu hồi/khóa tài khoản được giải quyết bằng cơ chế server-side khi cần. Order/Payment vẫn là dữ liệu bền vững.

### Bài toán C — Dịch vụ thanh toán không có phiên browser

Provider gửi webhook sau khi khách đã đóng trình duyệt. Payment Service xác minh chữ ký, tra attempt từ database, cập nhật kết quả idempotent và phát event. Session của người dùng không quyết định kết quả thanh toán.

### Bài toán D — Giỏ hàng có thể dùng xuyên thiết bị

Giỏ hàng đã được doanh nghiệp cam kết lưu nên thuộc một Cart/Ordering context hoặc nguồn dữ liệu phù hợp theo chính sách. Khi login trên thiết bị khác, API truy xuất giỏ sau khi xác thực. Không lưu toàn bộ giỏ chỉ trong HttpSession của một browser.

### Bài toán E — Job xử lý đơn chạy nền

Một worker nhận event OrderPlaced và xử lý tồn kho. Job state và idempotency nằm trong kho bền vững/queue theo thiết kế; không có cookie hay phiên người dùng. Nếu worker restart, có thể xử lý lại an toàn.

## 21. Checklist thiết kế trước khi triển khai

Đối với mỗi loại trạng thái, tự trả lời:

1. **Ý nghĩa:** trạng thái này mô tả một sự thật nghiệp vụ, một phiên xác thực, một thao tác request hay tài nguyên process?
2. **Chủ sở hữu:** service/context nào có quyền tạo và thay đổi?
3. **Durability:** nếu process restart, user logout hoặc cluster chuyển node thì dữ liệu có cần còn không?
4. **Consistency:** có bất biến nào phải bảo vệ bằng transaction, unique constraint hoặc version không?
5. **Lifespan:** hết hạn sau bao lâu, và ai chịu trách nhiệm dọn dữ liệu?
6. **Recovery:** timeout hay phản hồi mất thì xác minh/retry thế nào?
7. **Security:** dữ liệu có phải credential hoặc thông tin nhạy cảm không? Ai được đọc/sửa?
8. **Scaling:** request vào bất kỳ instance nào có cho kết quả hợp lệ không?
9. **Observability:** có tìm được trạng thái hiện tại, lịch sử, lỗi và hành động khôi phục không?
10. **Change:** khi schema hoặc auth policy đổi, các instance phiên bản cũ/mới có tương thích trong rollout không?

Một quyết định tốt thường ghi rõ ràng:

~~~text
State name: Order.paymentStatus
Type: business state projection
Owner: Ordering (nguồn sự thật giao dịch thuộc Payments)
Storage: Order Database
Lifetime: theo vòng đời và chính sách lưu đơn
Update: PaymentSucceeded/PaymentFailed qua consumer idempotent
Consistency: eventual across services; atomic within Ordering
Concurrency: version + transition rules
Recovery: reconcile với Payments nếu PENDING quá hạn
Security: chỉ user/actor được cấp quyền xem
Session dependency: none
~~~

## 22. Thực hành với một đơn hàng và hai phiên

### Bài 1 — Đóng trình duyệt giữa thanh toán

Khách có session S-A và tạo ORD-1001. Trình duyệt đóng; S-A hết hạn. Provider thông báo PaymentSucceeded. Hãy xác định dữ liệu nào bắt buộc phải còn, component nào cập nhật đơn và làm sao khách xem đơn vào ngày hôm sau.

**Gợi ý:** Payment attempt, orderId và kết quả nghiệp vụ phải tồn tại bền vững; webhook đi theo service identity; Ordering cập nhật qua kết quả của Payments. Khách đăng nhập bằng một session mới và kiểm tra quyền đọc order theo customerId.

### Bài 2 — Hai instance nhận cùng request tạo đơn

A và B gần như đồng thời nhận POST /orders cùng Idempotency-Key. Hãy thiết kế unique constraint/scope và phản hồi nhất quán để chỉ một đơn được tạo.

**Gợi ý:** Các instance dùng một nguồn idempotency dùng chung có tính nguyên tử; cùng key/payload trả kết quả của cùng operation; khác payload trả conflict.

### Bài 3 — Lưu giỏ trong HttpSession

Một người dùng muốn xem giỏ trên điện thoại và laptop. Hiện giỏ lưu trong session trên laptop. Đề xuất ranh giới nghiệp vụ và một API phù hợp để đồng bộ giỏ, kiểm tra quyền và xử lý sửa giỏ đồng thời.

**Gợi ý:** Xem giỏ như dữ liệu nghiệp vụ có owner/userId, kho lưu bền vững theo yêu cầu, version hoặc quy tắc merge rõ, không buộc hai thiết bị chia sẻ một session.

### Bài 4 — Session store mất kết nối

Trong 5 phút Redis session store không thể truy cập. Order Database vẫn hoạt động. Hệ thống có thể cho user chưa được xác thực cập nhật đơn không? Cách hiển thị lỗi và phục hồi nên ra sao?

**Gợi ý:** Fail closed cho thao tác cần auth; trả lỗi phù hợp, quan sát sự cố, tránh retry dồn dập và bảo vệ store. Không đánh đồng lỗi xác thực với mất dữ liệu nghiệp vụ.

### Bài 5 — Event đến trễ

ShipmentDelivered tới sau khi Order Service đã ghi trạng thái DELIVERED qua một nguồn khác. Hệ thống phải làm gì nếu event trùng? Nếu event chứa shipmentId không thuộc order thì sao?

**Gợi ý:** Kiểm tra quan hệ order–shipment và eventId; không lùi state; ghi nhận trùng an toàn và cảnh báo dữ liệu sai nguồn.

### Bài 6 — Logout toàn bộ thiết bị

User có ba access token còn hiệu lực. Doanh nghiệp yêu cầu thao tác “logout all devices” phải có hiệu lực nhanh. Hãy mô tả vì sao chỉ xóa cookie trên thiết bị hiện tại không đủ, và chọn cơ chế revocation dựa trên mức độ rủi ro.

**Gợi ý:** Phải quản lý trạng thái refresh token và kiểm tra hiệu lực access token theo chính sách (short lifetime, denylist, introspection hoặc account/token version) cùng giới hạn độ trễ chấp nhận.

## 23. Câu hỏi tự kiểm tra

1. Vì sao Order=PAID không nên được lưu làm một thuộc tính session rồi xóa khi logout?
2. Stateless instance có đồng nghĩa với việc cả hệ thống không chứa business state không?
3. Ba replica của Order Service có tự chia sẻ Map và biến static Java không?
4. Vì sao một orderId cần được phân quyền dựa vào danh tính/nghiệp vụ thay vì sessionId?
5. Transactional Outbox giải quyết tình huống mất event ở giai đoạn nào?
6. Saga state cần sống bao lâu khi callback từ cổng thanh toán đến sau khi browser đóng?
7. Khi hai request cùng sửa Order version=3, optimistic locking giúp phát hiện điều gì?
8. Sticky session có bảo đảm session và dữ liệu nghiệp vụ vẫn đúng khi instance bị thay thế không?
9. JWT đã ký có đồng nghĩa payload được mã hóa và không thể đọc không?
10. Với cookie-based authentication, vì sao vẫn phải xét CSRF và cookie flags?
11. Payment API timeout có đủ để kết luận chưa trừ tiền không?
12. Hai trạng thái StockReserved và PaymentSucceeded thuộc nguồn sở hữu nào và Ordering nên sử dụng chúng như thế nào?

## 24. Tổng kết

**Business state** phản ánh sự thật và nghĩa vụ của domain; nó có vòng đời, bất biến, chủ sở hữu và yêu cầu độ bền độc lập với phiên browser. **Session state** phản ánh ngữ cảnh tương tác/xác thực; nó có thể hết hạn, thu hồi và thay đổi theo thiết bị. **Request/UI state** và **runtime state** còn ngắn hạn hơn, thường không phù hợp làm nguồn sự thật nghiệp vụ.

Trong Microservices có nhiều instance, hãy thiết kế để request vào bất kỳ instance nào vẫn truy xuất đúng dữ liệu: business state nằm ở kho bền vững thuộc context sở hữu; session có cơ chế chia sẻ hoặc xác minh token được thiết kế rõ; cập nhật đồng thời được bảo vệ bằng transaction/version; thao tác có tác động phụ được idempotent; workflow liên dịch vụ có event, outbox, saga và reconciliation theo nhu cầu. Khi tách đúng các loại trạng thái, hệ thống có thể scale, restart, failover và xử lý callback đến muộn mà không đánh mất tính đúng đắn của nghiệp vụ.
