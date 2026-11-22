# Phân biệt một dịch vụ logic với nhiều thể hiện đang chạy

## 1. Vấn đề: Một tên dịch vụ có thể xuất hiện nhiều lần

Trong kiến trúc Microservices, ta thường nói “Order Service xử lý đơn hàng”, “Payment Service xác nhận thanh toán” hoặc “Inventory Service kiểm tra tồn kho”. Những tên gọi này diễn tả **dịch vụ theo trách nhiệm nghiệp vụ**. Nhưng khi triển khai thực tế, một dịch vụ có thể có **một, ba, mười hoặc nhiều tiến trình đang chạy đồng thời**.

Đây là hai cấp độ khác nhau:

- **Dịch vụ logic (logical service):** đơn vị chức năng có trách nhiệm, hợp đồng giao tiếp và ranh giới dữ liệu rõ ràng; ví dụ Order Service quản lý vòng đời đơn hàng.
- **Thể hiện đang chạy (service instance):** một bản thực thi cụ thể của dịch vụ tại một thời điểm; ví dụ một process Java chạy Order Service trong container trên một máy, có địa chỉ mạng và định danh riêng.

Một Order Service có ba instance vẫn là **một dịch vụ logic**, không trở thành ba Microservices nghiệp vụ khác nhau. Ngược lại, ba dịch vụ Order, Payment và Inventory là **ba dịch vụ logic riêng biệt**, dù mỗi dịch vụ hiện chỉ chạy một instance.

Bài học giúp bạn đọc đúng sơ đồ hệ thống, hiểu cách mở rộng và chịu lỗi, và tránh đặt trạng thái nghiệp vụ tại một instance bất kỳ rồi vô tình làm mất hoặc lệch dữ liệu khi tăng số lượng bản chạy.

## 2. Minh họa trực quan

Giả sử website bán hàng gọi API lấy thông tin đơn ORD-1001. Trong thiết kế hệ thống, ta có thể vẽ duy nhất một ô “Order Service”. Nhưng ở hạ tầng chạy thật, một bộ cân bằng tải có thể phân phối request đến ba instance.

~~~mermaid
flowchart TB
    C[Web / Mobile Client] --> G[API Gateway / Load Balancer]
    G --> S[Order Service - tên logic]
    S -. triển khai thành .-> A[Order Instance A<br/>10.0.1.11:8080]
    S -. triển khai thành .-> B[Order Instance B<br/>10.0.1.12:8080]
    S -. triển khai thành .-> D[Order Instance C<br/>10.0.1.13:8080]
    A --> DB[(Order Database)]
    B --> DB
    D --> DB
~~~

**Sơ đồ là mô hình khái niệm.** Trong đường mạng thật, Gateway hoặc bộ định tuyến có thể chọn instance trực tiếp; request không nhất thiết đi qua một chương trình “Order Service” trung gian. Ô “Order Service - tên logic” ở đây đại diện cho tập hợp instance cùng cung cấp hợp đồng dịch vụ.

Khi đọc sơ đồ:

1. Client cần **khả năng tạo hoặc đọc đơn hàng**, không cần biết máy nào đang chạy.
2. Bộ định tuyến có danh sách các endpoint của các instance sẵn sàng nhận lưu lượng.
3. Một request cụ thể được chuyển đến **một instance** phù hợp; request kế tiếp có thể đến instance khác.
4. Cả ba instance đều thực thi logic Order Service và truy cập nguồn dữ liệu đơn hàng được thiết kế chung.
5. Khi instance B mất khả năng phục vụ, A và C vẫn có thể tiếp tục xử lý request mới nếu hạ tầng và phụ thuộc bên dưới còn hoạt động.

Hình trên **không ngụ ý** rằng mọi instance phải kết nối trực tiếp vào cùng một máy database. Cơ sở dữ liệu có thể có leader, replica, proxy hoặc cụm phân tán; điểm chính là các instance cùng tuân theo **một ranh giới sở hữu dữ liệu nghiệp vụ của Order Service**.

## 3. Bảng phân biệt các khái niệm dễ nhầm

| Thuật ngữ | Bản chất | Ví dụ | Có đồng nghĩa với Microservice không? |
| --- | --- | --- | --- |
| Dịch vụ logic | Khả năng/nghiệp vụ và hợp đồng giao tiếp | Order Service | Đây là cấp độ kiến trúc dịch vụ |
| Codebase / module | Mã nguồn xây dựng dịch vụ | Repository hoặc module Order | Một codebase có thể sinh nhiều bản chạy |
| Artifact / image | Bản đóng gói có thể triển khai | Image order-service:1.4.0 | Là bản phát hành, chưa phải instance |
| Deployment | Khai báo mong muốn chạy một phiên bản và số replica | Deployment order-service, replicas=3 | Quản lý các bản chạy của một workload |
| Instance | Một quá trình thực thi cụ thể đang sống | Order tại 10.0.1.12:8080 | Là bản thực thi của dịch vụ |
| Container | Môi trường thực thi đóng gói process | Container JVM order-service | Thường chứa một instance ứng dụng, nhưng không bắt buộc một-một |
| Pod (Kubernetes) | Đơn vị lập lịch chứa một hoặc nhiều container | Pod order-service-abc | Một pod có thể gồm app container và sidecar |
| Endpoint | Địa chỉ có thể định tuyến đến thực thể phục vụ | IP:port của pod hoặc máy | Là điểm kết nối kỹ thuật |
| Kubernetes Service | Đối tượng mạng cung cấp địa chỉ và chọn backend | order-service.default.svc | Là cơ chế khám phá/định tuyến, không phải ranh giới nghiệp vụ |
| Replica | Một bản chạy mong muốn hoặc thực tế trong workload | replicas=3 | Liên quan số lượng instance, không nói có bao nhiêu dịch vụ logic |

Các tên trên thường liên hệ với nhau, nhưng không có quy tắc mọi **process = container = pod = deployment = dịch vụ logic**. Một pod có thể chứa nhiều container; một dịch vụ logic có thể có nhiều deployment hoặc phiên bản chạy đồng thời; một process có thể chứa nhiều thành phần ứng dụng. Khi thiết kế, hãy diễn đạt rõ cấp độ đang nói đến.

## 4. Ví dụ cụ thể: Order Service có ba instance

Order Service định nghĩa các API minh họa:

~~~http
POST /orders
GET /orders/{orderId}
POST /orders/{orderId}/cancel
~~~

Các instance A, B và C cùng chạy phiên bản tương thích của ứng dụng, cung cấp hợp đồng API tương đương. Tuy nhiên, mỗi instance có trạng thái vận hành riêng:

| Thuộc tính | Instance A | Instance B | Instance C |
| --- | --- | --- | --- |
| Dịch vụ logic | Order Service | Order Service | Order Service |
| Phiên bản ứng dụng (ban đầu) | 1.4.0 | 1.4.0 | 1.4.0 |
| Endpoint ví dụ | 10.0.1.11:8080 | 10.0.1.12:8080 | 10.0.1.13:8080 |
| Instance ID | order-a | order-b | order-c |
| Heap JVM và thread pool | Riêng | Riêng | Riêng |
| Bộ nhớ cache local | Riêng | Riêng | Riêng |
| Kết nối tới hạ tầng dữ liệu | Pool kết nối riêng | Pool kết nối riêng | Pool kết nối riêng |
| Dữ liệu đơn ORD-1001 | Đọc/ghi qua nguồn dữ liệu thuộc Order | Tương tự | Tương tự |

Hai người dùng cùng gọi GET /orders/ORD-1001 có thể được chuyển đến hai instance khác nhau. Kết quả nghiệp vụ cần phản ánh **cùng một đơn** dựa trên dữ liệu có thẩm quyền, dù địa chỉ của instance xử lý khác nhau.

Giả sử:

- 10:00:00 — request tạo đơn đến instance A; A lưu ORD-1001 thành công.
- 10:00:01 — request đọc đơn đến instance C; C truy vấn Order Database và trả ORD-1001.
- 10:00:02 — instance A bị dừng; request tiếp theo đến instance B.
- 10:00:03 — instance B vẫn đọc được ORD-1001 từ nguồn dữ liệu chung.

Nếu ORD-1001 chỉ được cất trong một Map ở bộ nhớ của A, C và B sẽ không thấy dữ liệu đó. Đây là lỗi điển hình khi lấy thiết kế chạy một process làm giả định cho hệ thống nhiều instance.

**Sự khác nhau cần nhớ:** cùng code và cùng trách nhiệm không đồng nghĩa cùng bộ nhớ RAM, cùng bộ đếm cục bộ, cùng socket, cùng thread hoặc cùng tiến trình lỗi.

## 5. Một request được định tuyến đến instance nào?

Một request HTTP gọi đến tên logic như api.shop.example/orders thường trải qua một tầng định tuyến: DNS, ingress, API Gateway, reverse proxy hoặc load balancer. Tầng này chọn một trong các backend hiện có thể phục vụ.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant G as Gateway / LB
    participant R as Registry / Endpoint Discovery
    participant A as Order A
    participant B as Order B
    participant D as Order DB

    G->>R: Lấy danh sách backend sẵn sàng (hoặc đã được cập nhật trước)
    R-->>G: A, B
    U->>G: GET /orders/ORD-1001
    G->>B: Chuyển request
    B->>D: SELECT order ORD-1001
    D-->>B: Dữ liệu đơn
    B-->>G: 200 OK
    G-->>U: 200 OK
~~~

Danh sách endpoint có thể được quản lý động. Bộ cân bằng tải có thể dùng round-robin, least-connections, weighted routing hoặc thuật toán khác. **Không có bảo đảm** rằng request của cùng một người dùng sẽ luôn đi vào cùng instance, trừ khi hệ thống cố tình dùng cơ chế affinity/sticky routing.

Chẳng hạn với một chuỗi request:

~~~text
Request 1: GET /orders/1001  -> Order A
Request 2: GET /orders/1001  -> Order C
Request 3: POST /orders      -> Order B
Request 4: GET /orders/1002  -> Order A
~~~

Chuỗi này chỉ minh họa khả năng phân phối; không phải lịch round-robin bắt buộc. Kết quả còn phụ thuộc connection reuse, thuật toán, health và chính sách mạng.

### Hai cách phổ biến để chọn backend

**Server-side load balancing:** Client gọi một địa chỉ ổn định; proxy, Gateway, ingress hoặc Service trong nền tảng chọn instance. Ví dụ client gọi Order Service qua một DNS nội bộ.

**Client-side load balancing:** Client hoặc SDK nắm danh sách endpoint từ service discovery và tự chọn instance. Cách này xuất hiện ở một số stack Java/Spring, nhưng không phải lựa chọn mặc định cho mọi hệ thống.

Cả hai đều giải quyết bài toán “tên dịch vụ logic → endpoint instance đang phục vụ”. Quyết định sử dụng cách nào phụ thuộc nền tảng, khả năng quan sát, bảo mật, vận hành và nhu cầu xử lý lỗi.

## 6. Service Discovery: tên ổn định và danh sách động

Nếu chỉ có một instance, bạn có thể tạm cấu hình địa chỉ cố định. Khi tăng lên nhiều instance, các IP/port có thể thay đổi vì:

- Pod được tạo lại sau lỗi hoặc sau một lần triển khai.
- Autoscaler tăng hoặc giảm số replica.
- Workload di chuyển giữa các máy.
- Phiên bản mới được triển khai song song với phiên bản cũ.
- Một instance chưa sẵn sàng hoặc đã bắt đầu quá trình shutdown.

**Service Discovery** giúp tầng gọi tìm đúng endpoint hiện hành. Có ba mô hình cần phân biệt:

1. **Cấu hình tĩnh:** địa chỉ IP/host được khai báo thủ công; đơn giản nhưng khó theo kịp các thay đổi tự động.
2. **Registry chuyên dụng:** instance hoặc nền tảng đăng ký, gia hạn, hủy đăng ký; client/proxy tra cứu registry và áp dụng health policy.
3. **Nền tảng điều phối như Kubernetes:** Deployment tạo/duy trì các pod, Service chọn các pod phù hợp qua label và cung cấp tên DNS ổn định; EndpointSlice/định tuyến của cluster cập nhật backend khả dụng.

Ví dụ trong Kubernetes, service bên gọi có thể sử dụng:

~~~text
http://order-service.default.svc.cluster.local
~~~

Tên trên **không** phải địa chỉ của một JVM cố định. Nó là tên mạng trỏ đến dịch vụ Kubernetes; hệ thống mạng đưa lưu lượng đến backend phù hợp với selector và trạng thái readiness.

Cũng cần phân biệt tên DNS, tên service logic, tên Deployment và tên container image: chúng có thể trùng cho dễ vận hành nhưng là các thực thể khác loại.

## 7. Mở rộng số instance không làm thay đổi ranh giới nghiệp vụ

Giả sử Order Service đang nhận lượng truy cập tăng. Một cách mở rộng theo chiều ngang là thay đổi số lượng instance:

~~~text
Trước cao điểm:  Order Service -> 1 instance
Trong cao điểm:  Order Service -> 4 instances
Sau cao điểm:    Order Service -> 2 instances
~~~

Đây là **horizontal scaling** (scale out / scale in). Ta thay đổi **sức xử lý của cùng một dịch vụ logic**, không tách thêm trách nhiệm Order thành những dịch vụ khác.

Ngược lại, **vertical scaling** tăng CPU/RAM cho instance hiện có. Hai cách có thể kết hợp, nhưng mỗi cách có giới hạn khác nhau.

Tăng instance có thể cải thiện:

- Số lượng request có thể xử lý song song.
- Khả năng thay thế một instance khi hỏng.
- Khả năng rollout cập nhật từng phần mà vẫn giữ dịch vụ phục vụ.

Nhưng tăng replica **không tự động** tăng gấp đôi throughput. Nếu mọi instance cùng phụ thuộc database quá tải, cổng thanh toán bị giới hạn request, lock tranh chấp hoặc queue chung bị nghẽn, bottleneck vẫn còn. Tổng connection pool cũng có thể tăng mạnh: 10 instance × 20 kết nối mỗi instance có thể tạo 200 kết nối database, chưa kể các thành phần khác.

### Tách hai loại chỉ số

**Chỉ số cấp dịch vụ logic:** tỷ lệ lỗi tổng, p95/p99 latency tổng, request rate, SLO của Order API, tỷ lệ tạo đơn thành công.

**Chỉ số cấp instance:** CPU, heap, GC, thread pool, số request đang xử lý, connection pool, restart count, tình trạng readiness của từng instance.

Một service có thể báo lỗi tổng tăng vì **một instance cụ thể** rò rỉ bộ nhớ. Ngược lại, mọi instance cùng chậm có thể do **phụ thuộc chung** như database hoặc broker.

## 8. Health check và vòng đời của instance

“Process đang chạy” không đồng nghĩa “instance đã sẵn sàng nhận request”. Cần hiểu ba loại kiểm tra thường dùng trong môi trường điều phối container:

| Kiểm tra | Câu hỏi | Tác động thường gặp |
| --- | --- | --- |
| Startup probe | Ứng dụng có đang khởi động thành công trong thời gian cho phép? | Tránh xử lý lỗi khởi động chậm như liveness thất bại quá sớm |
| Readiness probe | Instance có thể phục vụ lưu lượng mới ngay lúc này? | Không đưa backend chưa sẵn sàng vào tập nhận traffic |
| Liveness probe | Ứng dụng có còn hoạt động đúng ở mức kiểm tra sống? | Có thể kích hoạt khởi động lại instance bị kẹt |

Trong Kubernetes, liveness failure có thể khiến container bị restart, còn readiness failure thường loại pod khỏi các endpoint đang nhận traffic mà không nhất thiết restart. Không nên biến liveness thành một bài kiểm tra phụ thuộc xa quá nặng; database chập chờn có thể làm mọi pod bị restart liên tục và khiến sự cố xấu hơn.

Ví dụ khi triển khai phiên bản mới:

1. Nền tảng tạo Order instance D với image mới.
2. D khởi động JVM, cấu hình, kết nối các phụ thuộc cần thiết và chưa nhận traffic cho đến khi ready.
3. Readiness thành công; load balancer có thể đưa D vào tập backend.
4. Instance cũ A bắt đầu shutdown; hệ thống ngừng định tuyến request mới đến A và cho request đang xử lý thời gian hoàn tất.
5. A kết thúc; các instance còn lại tiếp tục phục vụ.

Quy trình thực tế còn phụ thuộc rolling-update strategy, termination grace period, connection draining và cấu hình health check. Cần bảo đảm phiên bản cũ/mới tương thích khi cùng chạy trong một giai đoạn.

## 9. Dữ liệu dùng chung và trạng thái cục bộ

Một instance có thể giữ bộ nhớ tạm để tăng tốc, nhưng phải xác định rõ dữ liệu đó có phải **nguồn sự thật nghiệp vụ** hay không.

### 9.1. Những gì thường nằm ở cấp instance

- Heap, stack, thread, socket đang mở.
- Cache trong process, connection pool, bộ đếm không đồng bộ.
- File tạm, log cục bộ, thông tin request đang xử lý.
- Mã định danh instance, hostname/pod name, PID.

Chúng có thể biến mất khi process restart hoặc node bị thay thế. Một instance khác không tự nhìn thấy những dữ liệu này.

### 9.2. Những gì cần có nguồn nhất quán theo dịch vụ

- Đơn hàng, thanh toán, tồn kho và trạng thái giao hàng.
- Quy tắc idempotency để tránh tạo đơn/thu tiền nhiều lần.
- Job hoặc lịch chạy cần không bị thực hiện trùng ngoài ý muốn.
- Phiên làm việc khi hệ thống yêu cầu người dùng đi qua nhiều instance.
- Trạng thái nghiệp vụ dài hạn và dữ liệu phục vụ audit/reconciliation.

Giải pháp tùy tính chất dữ liệu: database thuộc service, distributed cache thích hợp, lưu trữ dùng chung, message broker hoặc cơ chế điều phối. **Stateless instance** không có nghĩa “ứng dụng không có trạng thái”; nó nghĩa là trạng thái cần tồn tại xuyên request/instance không bị phụ thuộc vào duy nhất bộ nhớ cục bộ của một process.

### Ví dụ sai: biến static giữ đơn hàng

~~~java
// Ví dụ KHÔNG phù hợp với nhiều instance:
private static final Map<String, Order> ORDERS = new ConcurrentHashMap<>();

public void save(Order order) {
    ORDERS.put(order.id(), order);
}
~~~

A ghi ORD-1001 vào ORDERS của A; B có Map riêng nên không đọc được. ConcurrentHashMap chỉ giúp nhiều thread **trong cùng một JVM** truy cập an toàn; nó không biến dữ liệu thành phân tán.

### Cách tiếp cận phù hợp hơn

~~~java
@Service
public class OrderApplicationService {
    private final OrderRepository orderRepository;

    public OrderApplicationService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional
    public Order create(CreateOrderCommand command) {
        Order order = Order.from(command);
        return orderRepository.save(order);
    }

    @Transactional(readOnly = true)
    public Order get(String orderId) {
        return orderRepository.findById(orderId)
            .orElseThrow(() -> new OrderNotFoundException(orderId));
    }
}
~~~

Đoạn code là **ví dụ cấu trúc**: interface repository, constructor, command, domain model và exception cần được định nghĩa nếu chạy thật. Điểm chính là các instance sử dụng một lớp truy cập dữ liệu bền vững và giao dịch cục bộ phù hợp. Khi nhiều instance cùng cập nhật đơn, cần thêm **kiểm soát đồng thời** như optimistic locking/version hoặc update điều kiện để tránh lost update.

## 10. Nhiều instance làm lộ ra các lỗi trước đây không thấy

### 10.1. Đếm số đơn trong biến cục bộ

Nếu A có counter=10 và B có counter=8, không thể cộng/đọc một biến của một instance rồi xem đó là “tổng số đơn của service” mà không có thiết kế tổng hợp. Chỉ số telemetry nên được thu từ từng instance và tổng hợp theo label; dữ liệu nghiệp vụ cần nguồn có thẩm quyền.

### 10.2. Dùng khóa trong process để bảo vệ tài nguyên chung

~~~java
synchronized void reserveStock(String sku) {
    // ... thay đổi tồn kho ...
}
~~~

Từ khóa synchronized chỉ bảo vệ các thread dùng **cùng monitor trong một JVM**. Với A và B, hai lời gọi có thể chạy cùng lúc trên hai monitor khác nhau. Bất biến “không bán quá số lượng khả dụng” phải được bảo vệ tại ranh giới dữ liệu phù hợp: giao dịch database, optimistic lock, atomic update, serialized actor/queue hoặc cơ chế có tính chất tương đương.

### 10.3. Bấm thanh toán lại sau timeout

Request ban đầu có thể đã được xử lý tại A, nhưng phản hồi thất lạc. Lần retry có thể đi vào B. Nếu idempotency chỉ ghi nhận trong RAM của A, B có thể thu tiền lần thứ hai.

Cần idempotency key có **phạm vi và lưu trữ dùng chung**, gắn với tác vụ nghiệp vụ; Payment Service còn phải dùng hoặc đối soát idempotency tại cổng thanh toán bên ngoài.

### 10.4. Lưu session đăng nhập trong RAM của một instance

Lượt đăng nhập đi vào A, request sau đi vào C và C không thấy session. Biện pháp phù hợp thường là cơ chế xác thực không dựa vào instance cụ thể hoặc session store dùng chung. Sticky session có thể làm giảm biểu hiện lỗi trong ngắn hạn nhưng không giải quyết trường hợp A chết hoặc scale in.

### 10.5. Cron job được khởi động trong mọi replica

Nếu mỗi instance có lịch “gửi báo cáo mỗi đêm” thì triển khai bốn replica có thể gửi bốn bản. Cần thiết kế job owner riêng, distributed lease/lock có fencing phù hợp, scheduler tập trung hoặc thao tác idempotent. Không giả định “một dịch vụ logic” đồng nghĩa “một tiến trình chạy lịch”.

### 10.6. Consumer cùng đọc broker

Nhiều instance của một consumer có thể tham gia cùng **consumer group**, chia các partition/message theo cơ chế của broker. Tăng instance không đồng nghĩa mọi instance đều nhận một bản riêng của mọi event; cũng không đảm bảo throughput tăng nếu chỉ có ít partition. Consumer phải chống xử lý trùng và giữ thứ tự theo khóa nghiệp vụ khi cần.

### 10.7. Cache không nhất quán giữa instance

A cập nhật cache local cho ORD-1001, B vẫn giữ dữ liệu cũ. Các lựa chọn gồm TTL thích hợp, cơ chế invalidation/event, distributed cache hoặc không cache dữ liệu nhạy về độ mới. Không xem một local cache là bản gốc nghiệp vụ.

## 11. Điều gì xảy ra khi một instance bị lỗi?

Giả sử có ba instance Order A/B/C và bộ định tuyến nhận thấy B không còn healthy.

~~~mermaid
flowchart LR
    CL[Client] --> LB[Gateway / LB]
    LB --> A[Order A - ready]
    LB -. loại khỏi tuyến .-> B[Order B - lỗi]
    LB --> C[Order C - ready]
    A --> DB[(Order DB)]
    C --> DB
~~~

Request **mới** có thể được chuyển đến A hoặc C. Tuy nhiên, request **đang chạy trên B** có thể bị mất kết nối, trả 502/503/504 hoặc đã commit kết quả trước khi phản hồi bị mất.

Tình huống này cho thấy hai mục tiêu khác nhau:

1. **Availability:** còn instance khỏe để nhận lưu lượng.
2. **Correctness:** retry hoặc tiếp tục xử lý không được tạo hai đơn, trừ tồn kho hai lần hay thu tiền hai lần.

Cân bằng tải và health check hỗ trợ availability; lưu trữ bền vững, giao dịch cục bộ, idempotency, event/outbox và reconciliation hỗ trợ correctness. Có nhiều instance không tự bảo đảm toàn hệ thống không có điểm lỗi chung: database, broker, DNS, load balancer hoặc vùng hạ tầng vẫn có thể bị lỗi.

### Một ví dụ retry an toàn

1. Client gửi POST /orders với Idempotency-Key=checkout-abc.
2. A lưu ORD-1001 và khóa idempotency vào nguồn dữ liệu bền vững, nhưng mất kết nối trước khi trả phản hồi.
3. Client retry cùng request và cùng key; lần này đến C.
4. C tra cứu idempotency key và trả về kết quả gắn với ORD-1001, không tạo ORD-1002.
5. Client tiếp tục tra cứu trạng thái ORD-1001.

Cơ chế này yêu cầu ràng buộc unique/transaction phù hợp để hai instance không cùng thắng một race condition. Một bước “kiểm tra đã có key chưa” rồi “insert” tách rời, không có kiểm soát đồng thời, vẫn có thể tạo trùng.

## 12. Triển khai minh họa với Kubernetes

Ví dụ sau diễn đạt **một dịch vụ logic với ba replica**. Image và cấu hình health endpoint là ví dụ, cần thay bằng artifact thực tế khi thử nghiệm. Cấu hình tối giản được tách thành Deployment quản lý pod và Service chọn backend.

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
    spec:
      containers:
        - name: order-app
          image: registry.example.com/order-service:1.4.0
          ports:
            - containerPort: 8080
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: 8080
            initialDelaySeconds: 20
            periodSeconds: 20
---
apiVersion: v1
kind: Service
metadata:
  name: order-service
spec:
  selector:
    app: order-service
  ports:
    - port: 80
      targetPort: 8080
~~~

Ở đây:

- **replicas: 3** yêu cầu bộ điều phối cố gắng duy trì ba pod cho Deployment.
- **selector/matchLabels** giúp Deployment quản lý đúng tập pod của mình.
- **Service selector** chọn các pod có label app=order-service.
- **port 80 / targetPort 8080** cho phép client gọi cổng 80 của Service, ứng dụng chạy cổng 8080 trong container.
- **readinessProbe** quyết định khi nào pod có thể được đưa vào tập endpoint phục vụ.
- **livenessProbe** kiểm tra tình trạng sống của app container.

Trong môi trường Spring Boot, hai đường dẫn /actuator/health/readiness và /actuator/health/liveness chỉ hoạt động khi cấu hình Actuator và health probes tương ứng đã được bật và expose phù hợp. Manifest trên không bao gồm Secret, resource limits, security context, pod disruption budget hay cấu hình production đầy đủ.

### Xem số lượng và danh tính các bản chạy

Ví dụ các lệnh quan sát trong namespace hiện tại:

~~~bash
kubectl get deployment order-service
kubectl get pods -l app=order-service -o wide
kubectl get service order-service
kubectl get endpointslice -l kubernetes.io/service-name=order-service
~~~

Kết quả mong đợi ở mức khái niệm là **một Deployment**, **một Service object** và khoảng **ba pod** đã sẵn sàng sau khi triển khai ổn định. Khi đang rollout hoặc có lỗi, số pod thực tế và số ready có thể khác giá trị mong muốn.

Thử đổi số replica:

~~~bash
kubectl scale deployment order-service --replicas=5
kubectl get pods -l app=order-service
~~~

Bạn thay đổi số replica của workload; không tạo thêm năm dịch vụ nghiệp vụ Order. Lưu ý lệnh scale này có tác động đến cluster nên chỉ chạy trong môi trường thử nghiệm được phép quản lý.

## 13. Giao tiếp giữa các dịch vụ logic

Một Order Service có thể cần gọi Payment Service. Giả sử:

~~~text
Order Service  ->  Payment Service
3 instances       2 instances
~~~

Không có quan hệ “Order A chỉ gọi Payment A” hoặc “phải có số replica bằng nhau”. Một request từ Order B có thể được chọn chuyển đến Payment A, request tiếp theo đến Payment B. Mỗi service có quy mô, mục tiêu SLO và vòng đời riêng.

~~~mermaid
flowchart LR
    OA[Order A] --> PR[Payment service address]
    OB[Order B] --> PR
    OC[Order C] --> PR
    PR --> PA[Payment A]
    PR --> PB[Payment B]
~~~

Điều quan trọng khi gọi xuyên service là **contract**. Các instance Payment phải cùng đáp ứng phiên bản giao thức mà caller đang dùng; trong rolling deployment có thể tồn tại hai phiên bản phần mềm song song. Do đó nên dùng thay đổi API tương thích ngược, hoặc điều phối migration/schema/event version khi không thể giữ tương thích.

Khi Payment A lỗi, Order B có thể retry qua Payment B; nhưng với thao tác **tạo thanh toán**, retry chỉ an toàn nếu bảo đảm idempotency và đã xác minh kết quả trước đó. Không tự kết luận thao tác đã thất bại chỉ vì kết nối timeout.

## 14. Theo dõi dịch vụ logic và instance đúng cấp

Khi hệ thống chậm, câu hỏi ban đầu có thể là “Order Service có đang lỗi không?”. Để xác định nguyên nhân cần drill down đến instance:

| Tầng quan sát | Thông tin nên có | Giúp phát hiện |
| --- | --- | --- |
| Service logic | service.name=order-service, traffic, error rate, latency | Người dùng đang bị ảnh hưởng mức nào |
| Deployment / version | phiên bản image, thời điểm rollout, desired/ready replicas | Lỗi có bắt đầu sau khi phát hành? |
| Instance | instance.id/pod name, node, CPU, heap, GC, thread pool | Một bản chạy cụ thể có bất thường không |
| Request / trace | traceId, spanId, requestId, orderId an toàn | Request đi qua instance và phụ thuộc nào |
| Dependency | DB connections, queue lag, downstream timeout | Sự cố có phải từ tài nguyên chung không |

Ví dụ log minh họa:

~~~text
service=order-service instance=order-a traceId=t-001 orderId=ORD-1001 status=200
service=order-service instance=order-c traceId=t-002 orderId=ORD-1001 status=200
service=order-service instance=order-b traceId=t-003 orderId=ORD-1002 status=503
~~~

Nếu chỉ lọc service=order-service, bạn sẽ thấy tỷ lệ lỗi của cả nhóm. Nếu nhóm theo instance, bạn có thể nhận ra B đang gây phần lớn 503. Nếu cả A/B/C đều lỗi khi gọi database, nguyên nhân có thể là phụ thuộc chung.

Định danh **service.name** nên ổn định giữa các lần triển khai để tổng hợp số liệu; **instance.id** phải đủ khác biệt giữa các bản chạy để hỗ trợ debug. Sau khi restart, một pod hoặc tiến trình mới có thể nhận định danh khác. Không dùng địa chỉ IP như mã định danh nghiệp vụ của đơn hàng.

## 15. Các lỗi tư duy thường gặp

**“Tôi đã tạo ba pod nên tôi có ba Microservices.”** Nếu chúng đều chạy Order API và cùng đảm nhận một bounded context, bạn có ba instance của **một** Microservice.

**“Mỗi instance phải có database riêng.”** Ranh giới sở hữu dữ liệu thường nằm ở **dịch vụ logic**. Tự chia mỗi instance một database độc lập mà không có chiến lược đồng bộ/sharding sẽ làm cùng một đơn xuất hiện không nhất quán. Một hệ thống phân tán có thể có shard/replica database, nhưng đó là bài toán dữ liệu riêng.

**“Chỉ cần tăng replicas là hết lỗi.”** Replica thêm năng lực xử lý ở tầng ứng dụng, nhưng không giải quyết nghẽn phụ thuộc hoặc lỗi logic bị nhân bản trên mọi instance.

**“Một request luôn ở cùng server vì client giữ kết nối.”** Điều này phụ thuộc proxy, connection reuse, HTTP version, load-balancing và session affinity. Ứng dụng nghiệp vụ không nên đặt tính đúng đắn vào giả định ngầm đó.

**“Readiness và liveness giống nhau.”** Readiness trả lời có nên gửi lưu lượng mới hay không; liveness phục vụ phát hiện tình trạng cần restart. Dùng sai có thể gây restart hàng loạt.

**“Có synchronized rồi nên không còn race condition.”** synchronized chỉ khóa trong cùng JVM. Nhiều instance cần cơ chế kiểm soát đồng thời ở tài nguyên chung.

**“Restart instance không thể mất dữ liệu.”** Dữ liệu chỉ được bảo toàn nếu đã được lưu trong hạ tầng bền vững hoặc cơ chế phù hợp. Bộ nhớ process, file tạm và request đang xử lý có thể mất.

**“Kubernetes Service là một tiến trình chạy nghiệp vụ.”** Kubernetes Service thường là đối tượng định tuyến ổn định đến backend pod; mã xử lý Order nằm trong các app container.

## 16. Bài thực hành suy luận

### Bài A — Đếm đúng thực thể

Một hệ thống có:

- Order Service: 4 pod chạy cùng Order API.
- Payment Service: 2 pod chạy cùng Payment API.
- Inventory Service: 3 pod chạy cùng Inventory API.

Hỏi: Có bao nhiêu dịch vụ logic? Có bao nhiêu pod ứng dụng theo mô tả? Nếu Order tăng từ 4 lên 8 pod thì số dịch vụ logic là bao nhiêu?

**Gợi ý:** Đếm **trách nhiệm/hợp đồng nghiệp vụ** để có số dịch vụ logic; đếm **bản chạy** để có số pod. Ở trạng thái mô tả ban đầu có **3 dịch vụ logic và 9 pod ứng dụng**; khi Order tăng lên 8 pod, vẫn có **3 dịch vụ logic**, tổng cộng **13 pod ứng dụng** (giả sử các nhóm khác không đổi và một pod tương ứng một bản chạy app trong bài toán).

### Bài B — Dữ liệu biến mất

A nhận POST tạo đơn và lưu vào HashMap local. B nhận GET đọc đơn ngay sau đó nhưng trả 404. Hãy chỉ ra nguyên nhân và cách sửa ở cấp kiến trúc.

**Gợi ý:** Hai JVM không chia sẻ HashMap. Lưu đơn vào nguồn dữ liệu có thẩm quyền thuộc Order Service; cân nhắc transaction, cache consistency và idempotency.

### Bài C — Một pod bị lỗi

Order có ba instance A/B/C. B bị lỗi; Gateway dừng gửi request mới đến B. Vậy mọi request đang chạy trên B có chắc chắn thành công không? Nếu POST /orders đã commit nhưng mất phản hồi, phải retry thế nào?

**Gợi ý:** Health routing chỉ xử lý request mới. Dùng idempotency key có lưu trữ và kiểm soát đồng thời dùng chung để retry không tạo đơn trùng.

### Bài D — Số replica tăng nhưng hiệu năng không đổi

Order tăng từ 2 lên 10 instances nhưng p95 latency vẫn tăng và database đạt giới hạn kết nối. Cần quan sát chỉ số nào? Giảm connection pool, tối ưu query, cache, giới hạn concurrency hoặc scale database có thể giúp trong điều kiện nào?

**Gợi ý:** Đo request rate, p95 latency, DB pool usage, query latency, lock contention và total connection count. Không đánh giá hiệu năng chỉ qua số pod.

### Bài E — Lịch chạy ban đêm

Ứng dụng Order có cron gửi email tổng kết mỗi ngày. Khi tăng từ một lên bốn instance, email được gửi bốn lần. Hãy đề xuất cơ chế bảo đảm tác vụ logic chỉ thực hiện theo chính sách một lần hoặc xử lý trùng an toàn.

**Gợi ý:** Đưa lịch vào một thành phần scheduler có quản lý sở hữu, hoặc dùng distributed lease và idempotency key theo ngày/đối tượng. Cần xử lý cả trường hợp worker chết giữa chừng.

## 17. Kiểm tra nhanh

1. Một tên dịch vụ logic có thể trỏ đến bao nhiêu instance?
2. Hai instance cùng chạy một image có chia sẻ biến static Java không?
3. Kubernetes Deployment, Pod và Service object khác nhau thế nào?
4. Vì sao readiness failure có thể làm giảm số backend nhận traffic mà không cần xóa dịch vụ logic?
5. Khi tăng replica, những tài nguyên dùng chung nào có thể trở thành bottleneck?
6. Tại sao idempotency lưu trong RAM của một instance không đủ an toàn cho retry?
7. Service discovery và load balancer giải quyết hai phần nào của bài toán định tuyến?
8. Chỉ số nào nên gắn với service.name, chỉ số nào cần instance.id?

Bạn nắm được chủ đề khi có thể giải thích rằng **dịch vụ logic là “ai chịu trách nhiệm và cung cấp hợp đồng gì”, còn instance là “bản thực thi cụ thể nào đang phục vụ tại thời điểm này”**. Thiết kế một dịch vụ có thể chạy nhiều instance đòi hỏi xử lý rõ việc định tuyến, quản lý trạng thái, lỗi giữa chừng, tương thích phiên bản, dữ liệu dùng chung và quan sát hệ thống.
