# Chọn layer và tier theo yêu cầu hệ thống thay vì theo số thư mục

Bài học này thuộc module **SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED**, trong chương **Lựa chọn và tiến hóa kiến trúc**. Module hướng tới cách tổ chức phần mềm theo kiến trúc phân tầng, với các trách nhiệm như presentation, application, business/domain và data access được phân định rõ. Khi chọn kiến trúc, cần phân biệt hai quyết định: chia trách nhiệm logic thành các layer và bố trí các thành phần thành những tier triển khai. Hai quyết định có liên quan nhưng không đồng nhất.

Số thư mục, package hoặc module trong repository không quyết định ứng dụng cần bao nhiêu layer hay bao nhiêu tier. Một ứng dụng có thể có nhiều layer logic nhưng được triển khai trong một tiến trình duy nhất. Ngược lại, một hệ thống có thể triển khai nhiều tiến trình hoặc dịch vụ trên nhiều máy dù mỗi tiến trình bên trong vẫn có các layer riêng. Cần chọn dựa trên yêu cầu nghiệp vụ, chất lượng hệ thống, ràng buộc dữ liệu, quy mô nhóm và năng lực vận hành.

## 1. Phân biệt layer logic và tier triển khai

### 1.1. Layer mô tả trách nhiệm và phụ thuộc

Layer là cách chia hệ thống theo trách nhiệm logic. Mỗi layer có nhiệm vụ và hợp đồng cộng tác riêng. Trong một ứng dụng Java/Spring, có thể gặp các trách nhiệm:

- **Presentation:** nhận yêu cầu từ HTTP, giao diện, CLI hoặc message; kiểm tra cấu trúc đầu vào và định dạng kết quả theo giao thức.
- **Application:** điều phối ca sử dụng, gọi các thành phần cần thiết, xác định transaction boundary và phối hợp side effect.
- **Business/domain:** biểu diễn khái niệm, quy tắc, chính sách và bất biến nghiệp vụ.
- **Data access/infrastructure:** truy cập database, filesystem, message broker và dịch vụ bên ngoài; triển khai các adapter kỹ thuật.

Đây là cách phân chia theo trách nhiệm, không phải công thức bắt buộc phải có đúng bốn layer. Một ứng dụng CRUD nhỏ có thể chỉ cần controller, service và repository. Một miền phức tạp có thể cần thêm domain service, policy, adapter hoặc module riêng. Có thể gộp hoặc tách trách nhiệm khi ranh giới thay đổi có lý do rõ ràng.

Điều quan trọng là phụ thuộc giữa các phần phải có chủ đích. Ví dụ, controller gọi application use case; application sử dụng hợp đồng cần thiết để đọc/ghi; adapter persistence triển khai hợp đồng đó. Quy tắc nghiệp vụ không nên phụ thuộc trực tiếp vào HTTP request hoặc chi tiết bảng dữ liệu chỉ vì các thành phần đang nằm trong cùng một ứng dụng.

### 1.2. Tier mô tả nơi thành phần chạy

Tier là đơn vị triển khai hoặc môi trường thực thi được phân tách. Tùy cách dùng thuật ngữ của từng tổ chức, tier có thể là máy, container, tiến trình hoặc nhóm dịch vụ có ranh giới triển khai và giao tiếp riêng.

Ví dụ:

- **Một tier triển khai:** toàn bộ ứng dụng và truy cập dữ liệu chạy trong một tiến trình hoặc một đơn vị triển khai; database có thể là tài nguyên bên ngoài được quản lý riêng, nên cần nêu rõ quy ước đếm tier của dự án.
- **Hai tier:** client chạy ở một nơi, backend chạy ở nơi khác; backend có thể kết nối trực tiếp database hoặc thông qua dịch vụ dữ liệu.
- **Ba tier triển khai:** presentation, application và data được đặt trong các đơn vị triển khai riêng, giao tiếp qua mạng hoặc giao thức xác định.
- **Nhiều tier/dịch vụ:** các phần được tách thành nhiều tiến trình hoặc dịch vụ độc lập, có thể triển khai và mở rộng riêng.

Một số tài liệu dùng cụm “three-tier architecture” để chỉ cách tách presentation, application và data thành ba tầng. Cách gọi này đôi khi trộn lẫn khái niệm trách nhiệm logic với cách bố trí vật lý. Khi thiết kế, hãy nói rõ phần nào là layer logic, phần nào là deployment tier, và vẽ cả hai góc nhìn nếu cần.

### 1.3. Ví dụ cùng layer nhưng khác tier

| Cấu trúc logic | Cách triển khai | Ý nghĩa |
|---|---|---|
| Controller, application service, domain, repository | Một ứng dụng Spring Boot chạy trong một tiến trình; database là dịch vụ riêng | Nhiều layer logic, một backend deployable |
| Presentation, application, data access | Ba tiến trình riêng giao tiếp qua HTTP hoặc protocol phù hợp | Layer được phân bố thành nhiều tier |
| Mỗi service có controller, application/domain và adapter riêng | Nhiều service độc lập, mỗi service có thể chạy nhiều replica | Các service là đơn vị triển khai; bên trong mỗi service vẫn có layer |
| Một ứng dụng chia package theo trách nhiệm | Một container duy nhất | Nhiều package không đồng nghĩa nhiều tier |

Sơ đồ khái niệm:

```text
Góc nhìn layer logic trong một ứng dụng
+--------------------------------------+
| Presentation                         |
+--------------------------------------+
| Application                          |
+--------------------------------------+
| Business / Domain                    |
+--------------------------------------+
| Data access / Infrastructure         |
+--------------------------------------+
              |
              v
       Database / External systems

Góc nhìn triển khai có thể là
+--------------------------------------+
| Một backend deployable               |
|  - Presentation                      |
|  - Application                       |
|  - Business / Domain                 |
|  - Data access adapter               |
+--------------------------------------+
              |
              v
       Database service
```

Sơ đồ cho thấy các layer có thể nằm chung trong một đơn vị triển khai. Nếu sau này tách application thành dịch vụ riêng, đó là thay đổi topology triển khai và giao tiếp, không chỉ là đổi tên folder.

## 2. Vì sao không nên chọn theo số thư mục?

Tạo các folder `controller`, `service`, `domain`, `repository` có thể giúp mã dễ tìm, nhưng tự nó không tạo ra kiến trúc tốt. Nếu controller vẫn truy vấn database trực tiếp, domain vẫn import Spring MVC, hoặc service chứa toàn bộ quy tắc và side effect, cấu trúc folder không bảo vệ được ranh giới.

Tương tự, tách một folder thành nhiều package hoặc module Gradle không tự động cần thêm deployment tier. Package và module chủ yếu giúp tổ chức mã, kiểm soát visibility và dependency ở thời điểm biên dịch. Tier liên quan đến tiến trình, môi trường, triển khai, giao tiếp và vận hành.

Một số quyết định sai thường gặp:

- Mỗi layer được đặt thành một dịch vụ riêng chỉ vì muốn “đúng kiến trúc ba tầng”.
- Tạo thêm folder cho từng loại class dù không có trách nhiệm độc lập.
- Tách database thành một dịch vụ qua HTTP chỉ để layer data access có vẻ độc lập.
- Gộp mọi thứ vào một package vì ứng dụng chỉ deploy một lần, khiến trách nhiệm bị trộn lẫn.
- Đếm số module Gradle rồi kết luận hệ thống có cùng số tier.

Hãy bắt đầu từ câu hỏi: phần nào có lý do thay đổi khác nhau, phần nào cần ranh giới bảo mật hoặc triển khai riêng, và chi phí giao tiếp mới có được lợi ích tương xứng hay không?

## 3. Các yêu cầu nên chi phối quyết định layer

Layer logic cần giúp kiểm soát thay đổi và phụ thuộc. Các yếu tố sau thường quyết định nên gộp hay tách trách nhiệm.

### 3.1. Độ phức tạp nghiệp vụ

Nếu ứng dụng chủ yếu là CRUD với ít quy tắc, controller, application service và repository có thể đã đủ. Tạo domain model giàu hành vi, nhiều mapper và interface cho mọi class có thể tăng chi phí mà không giải quyết vấn đề cụ thể.

Nếu miền có nhiều bất biến, trạng thái, chính sách và luồng sử dụng khác nhau, cần ranh giới domain rõ hơn. Application service điều phối ca sử dụng; domain model bảo vệ quy tắc; adapter cô lập database hoặc dịch vụ ngoài. Các layer giúp thay đổi giao diện hoặc lưu trữ mà ít ảnh hưởng tới quy tắc.

### 3.2. Số lượng giao diện và cách gọi

Một ca sử dụng được gọi từ REST API, tác vụ theo lịch và message consumer có thể hưởng lợi từ application contract dùng chung. Presentation adapter và messaging adapter chuyển đổi payload thành command phù hợp, còn application điều phối cùng một hành vi.

Nếu chỉ có một giao diện đơn giản, chưa cần tạo nhiều adapter dự phòng. Nhưng nếu nhiều đường gọi đang tự cài lại quy tắc, đó là dấu hiệu nên tách hợp đồng và trách nhiệm.

### 3.3. Khả năng thay đổi công nghệ

Nếu schema database thay đổi thường xuyên, hoặc hệ thống cần hỗ trợ nhiều nguồn dữ liệu, persistence adapter và hợp đồng truy cập dữ liệu rõ ràng có thể giảm phạm vi ảnh hưởng. Nếu ứng dụng ổn định và entity JPA có cùng ngữ nghĩa với mô hình nội bộ, dùng chung entity có thể là lựa chọn thực dụng.

Không cần tạo interface cho mọi repository nếu chưa có lý do thay thế, kiểm thử hoặc bảo vệ dependency. Abstraction có giá trị khi nó biểu diễn hợp đồng mà phía gọi thực sự cần.

### 3.4. Ranh giới sở hữu và phối hợp nhóm

Khi nhiều nhóm cùng phát triển, module hoặc layer có hợp đồng rõ giúp giảm việc sửa trực tiếp mã của nhau. Tuy nhiên, chia package theo sơ đồ tổ chức nhóm có thể làm một ca sử dụng phải đi qua quá nhiều lớp điều phối. Cần cân bằng giữa ranh giới kỹ thuật và luồng nghiệp vụ thực tế.

## 4. Các yêu cầu nên chi phối quyết định tier

Tách thành nhiều tier làm thay đổi cách hệ thống giao tiếp, triển khai và chịu lỗi. Chỉ nên tách khi có yêu cầu đủ rõ.

### 4.1. Mở rộng tải độc lập

Nếu phần xử lý HTTP cần nhiều replica nhưng tác vụ nền tiêu thụ tài nguyên khác, tách worker khỏi web application có thể cho phép scale độc lập. Nếu toàn bộ ứng dụng có tải tương đối đồng đều, một backend có thể scale bằng cách tăng số replica mà không cần tách từng layer thành dịch vụ.

Tách một tier chỉ hữu ích khi có thể đo và quản lý nhu cầu riêng. Nếu các phần luôn phải scale cùng nhau, việc tách có thể tăng chi phí mà không tạo hiệu quả đáng kể.

### 4.2. Tính sẵn sàng và cô lập lỗi

Một tiến trình riêng có thể giúp cô lập lỗi hoặc tài nguyên, nhưng cũng tạo thêm một dependency qua mạng. Khi một service không phản hồi, caller cần timeout, retry có giới hạn, circuit breaker hoặc phương án fallback phù hợp. Nhiều tier không tự động làm hệ thống sẵn sàng hơn; nó có thể tạo thêm điểm lỗi và tình huống kết quả không xác định.

Nếu một phần xử lý không quan trọng với phản hồi đồng bộ, có thể chuyển thành tác vụ nền hoặc message để giảm phụ thuộc trực tiếp. Cách này cần chấp nhận độ trễ và thiết kế tính nhất quán phù hợp.

### 4.3. Bảo mật và vùng tin cậy

Tách tier có thể tạo ranh giới mạng và quyền truy cập. Ví dụ, database chỉ cho phép backend kết nối, còn browser client không bao giờ truy cập trực tiếp database. Một dịch vụ xử lý dữ liệu nhạy cảm có thể được đặt trong mạng riêng với quyền hạn hẹp.

Tuy nhiên, thêm tier không tự động bảo mật. Mỗi kết nối mới cần xác thực, phân quyền, mã hóa, quản lý secret và giám sát. Ranh giới bảo mật phải được xác định theo dữ liệu và mối đe dọa thực tế, không chỉ theo sơ đồ triển khai.

### 4.4. Độ trễ và giao tiếp

Lời gọi trong cùng tiến trình thường tránh được serialization và network round trip. Khi tách thành dịch vụ, mỗi giao tiếp cần xử lý latency, timeout, retry, version contract và lỗi kết nối. Một ca sử dụng gọi tuần tự năm dịch vụ có thể tăng độ trễ đáng kể.

Nếu nhiều thao tác cần một transaction ACID duy nhất, tách chúng sang các database/dịch vụ độc lập sẽ làm bài toán nhất quán phức tạp hơn. Khi đó cần xem xét transaction phân tán, outbox, saga hoặc điều chỉnh ranh giới dữ liệu. Không nên tách một phần chỉ vì layer đó có một folder riêng.

### 4.5. Năng lực vận hành

Mỗi tier độc lập cần pipeline build/deploy, cấu hình, secret, logging, metrics, tracing, health check, cảnh báo, quản lý phiên bản và hỗ trợ sự cố. Nhóm cần đủ năng lực để vận hành những thành phần này.

Một ứng dụng modular monolith có thể giúp giữ ranh giới mã rõ ràng mà vẫn chỉ cần một pipeline triển khai chính. Khi nhu cầu scale, bảo mật hoặc sở hữu độc lập xuất hiện, một module có thể được tách ra với hợp đồng đã được chuẩn bị.

## 5. So sánh một số cách bố trí phổ biến

| Cách bố trí | Khi thường phù hợp | Đánh đổi cần hiểu |
|---|---|---|
| Layered monolith | Ứng dụng có một đơn vị triển khai chính, các phần cùng release và cần giao dịch nội bộ đơn giản | Scale theo ứng dụng; cần giữ dependency giữa layer rõ ràng |
| Modular monolith | Nhiều khu vực nghiệp vụ cần ranh giới module nhưng chưa cần deploy riêng | Vẫn có thể có coupling nếu module API không được kiểm soát |
| Client-server | Giao diện và backend cần tách môi trường hoặc vùng tin cậy | Phát sinh giao tiếp mạng và quản lý phiên bản API |
| Three-tier deployment | Presentation, application và data cần được triển khai/quản trị tách biệt | Thêm network hop, cấu hình và vận hành |
| Microservices | Các miền cần sở hữu, phát hành và scale độc lập; nhóm có năng lực vận hành phân tán | Tăng độ phức tạp dữ liệu, quan sát, bảo mật và giao tiếp liên dịch vụ |

Các cách bố trí này không phải những bậc bắt buộc phải đi qua. Một hệ thống có thể ở dạng layered monolith trong nhiều năm và vẫn là lựa chọn tốt. Một hệ thống khác có thể cần một số dịch vụ độc lập vì ranh giới dữ liệu, tải hoặc tổ chức nhóm. Không nên xem microservices là giai đoạn tiến hóa bắt buộc của layered architecture.

## 6. Ví dụ Java/Spring: nhiều layer trong một backend deployable

Một ứng dụng bán hàng có thể tổ chức mã theo trách nhiệm trong một Spring Boot application:

```text
com.example.orders
  presentation/
    OrderController
    OrderHttpMapper
  application/
    PlaceOrderUseCase
    PlaceOrderService
    PlaceOrderCommand
  domain/
    Order
    OrderLine
    OrderPolicy
  infrastructure/
    persistence/
      JpaOrderRepository
      OrderJpaEntity
    messaging/
      OrderEventPublisher
```

Đây là một cách tổ chức package minh họa. Tất cả có thể được đóng gói trong cùng một JAR/container và triển khai như một backend duy nhất. Database có thể chạy như một dịch vụ riêng được quản lý bởi nền tảng.

Luồng gọi có thể như sau:

```text
HTTP Request
     |
     v
OrderController
     |
     v
PlaceOrderService
     |
     +----> Domain: Order.place(...)
     |
     +----> OrderRepository (contract)
                    |
                    v
            JpaOrderRepository
                    |
                    v
                Database
```

Một controller có thể rất mỏng:

```java
@RestController
@RequestMapping("/orders")
class OrderController {
    private final PlaceOrderUseCase placeOrder;

    OrderController(PlaceOrderUseCase placeOrder) {
        this.placeOrder = placeOrder;
    }

    @PostMapping
    ResponseEntity<OrderResponse> create(
            @Valid @RequestBody CreateOrderRequest request) {
        OrderId id = placeOrder.handle(
                new PlaceOrderCommand(
                        request.customerId(),
                        request.lines()));

        return ResponseEntity
                .created(URI.create("/orders/" + id.value()))
                .body(new OrderResponse(id.value()));
    }
}
```

Application service điều phối ca sử dụng và có thể xác định transaction:

```java
@Service
class PlaceOrderService implements PlaceOrderUseCase {
    private final OrderRepository orders;

    PlaceOrderService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public OrderId handle(PlaceOrderCommand command) {
        Order order = Order.place(command);
        orders.save(order);
        return order.id();
    }
}
```

Đoạn code rút gọn để minh họa hướng phân chia trách nhiệm. Domain model có thể là Java thuần; persistence adapter ánh xạ sang entity JPA. Nhưng nếu ứng dụng ít quy tắc, nhóm có thể dùng mô hình đơn giản hơn. Không cần nhân bản mọi kiểu dữ liệu hoặc tạo package con chỉ để đủ số layer.

## 7. Ví dụ cùng hệ thống khi cần thêm tier

Giả sử tải HTTP tăng mạnh nhưng tác vụ tạo báo cáo chạy lâu và tiêu thụ CPU. Nhóm có thể tách worker thành một đơn vị triển khai riêng, trong khi giữ nguyên các layer logic cần thiết:

```text
                    +----------------------+
Client ------------>| Web application      |
                    | Presentation         |
                    | Application          |
                    | Domain                |
                    | Persistence adapter  |
                    +----------+-----------+
                               |
                         Database / Outbox
                               |
                               v
                    +----------------------+
                    | Background worker    |
                    | Message adapter      |
                    | Application          |
                    | Domain               |
                    | Persistence adapter  |
                    +----------------------+
```

Web application và worker là hai deployment unit. Mỗi tiến trình có thể chứa application/domain và adapter phù hợp với nhiệm vụ. Hai tiến trình có thể dùng chung một số module Java hoặc thư viện domain nếu hợp đồng và vòng đời phù hợp, nhưng phải thống nhất cách truy cập dữ liệu và xử lý message lặp.

Tách worker có thể cho phép scale độc lập và giới hạn tài nguyên. Đổi lại, hệ thống cần message broker, retry, dead-letter handling, idempotency, observability và cơ chế phối hợp dữ liệu. Nếu báo cáo chỉ chạy vài lần mỗi ngày và không ảnh hưởng web latency, có thể một worker đơn giản hoặc scheduler trong cùng ứng dụng đã đủ.

## 8. Đưa ra quyết định bằng yêu cầu và đánh đổi

Một quyết định layer/tier nên dựa trên các driver đã xác định, không dựa vào sở thích công nghệ.

Có thể đi theo trình tự:

1. **Xác định hành vi nghiệp vụ:** những ca sử dụng nào quan trọng, quy tắc nào cần bảo vệ, dữ liệu nào phải nhất quán?
2. **Xác định quality attributes:** latency, throughput, availability, security, modifiability, testability và khả năng vận hành quan trọng tới mức nào?
3. **Xác định ranh giới logic:** trách nhiệm nào thay đổi độc lập, nơi nào sở hữu quy tắc và hợp đồng nào cần được giữ ổn định?
4. **Xác định nhu cầu triển khai:** phần nào cần scale, release, cô lập lỗi hoặc đặt trong vùng mạng riêng độc lập?
5. **Kiểm tra dữ liệu và transaction:** các phần có cần cùng commit không, có thể chấp nhận eventual consistency không?
6. **Ước lượng chi phí vận hành:** pipeline, monitoring, tracing, bảo mật, hỗ trợ sự cố và năng lực nhóm đã sẵn sàng chưa?
7. **Chọn phương án đơn giản đáp ứng yêu cầu:** ghi lại lý do, rủi ro và điều kiện xem xét lại.
8. **Xác minh bằng đo lường:** dùng workload, benchmark, production metrics hoặc thử nghiệm giới hạn để kiểm tra giả định.

Một bảng so sánh quyết định có thể giúp nhóm trao đổi:

| Driver | Giữ một deployable | Tách thêm tier/service |
|---|---|---|
| Tải | Các phần có profile tải tương tự | Một phần có tải hoặc tài nguyên khác biệt rõ |
| Release | Các phần thường thay đổi cùng nhau | Cần phát hành độc lập thường xuyên |
| Dữ liệu | Cần transaction chung và chia sẻ dữ liệu chặt | Có ranh giới dữ liệu rõ, chấp nhận giao tiếp bất đồng bộ |
| Bảo mật | Một backend trong vùng tin cậy đáp ứng yêu cầu | Cần vùng mạng/quyền truy cập tách biệt |
| Độ trễ | Nhiều lời gọi nội bộ cần nhanh | Chấp nhận network hop và timeout có kiểm soát |
| Vận hành | Nhóm muốn một pipeline và runtime đơn giản | Nhóm đủ năng lực vận hành nhiều deployable |
| Sở hữu | Một nhóm hoặc nhóm phối hợp chặt | Nhóm có quyền sở hữu và hợp đồng độc lập |

Bảng không đưa ra câu trả lời tự động. Một driver có thể quan trọng hơn các driver khác. Ví dụ, yêu cầu cô lập dữ liệu nhạy cảm có thể buộc tách một tier dù tải chưa lớn. Ngược lại, nhu cầu scale độc lập nhỏ có thể được giải quyết bằng worker hoặc replica trước khi tách nhiều dịch vụ.

## 9. Khi nào cần thay đổi kiến trúc?

Kiến trúc nên tiến hóa khi có bằng chứng rằng cách tổ chức hiện tại không còn đáp ứng yêu cầu. Các dấu hiệu có thể gồm:

- Một khu vực thường xuyên gây nghẽn và cần scale độc lập.
- Một nhóm bị chặn phát hành vì phải chờ release toàn ứng dụng.
- Quy tắc nghiệp vụ bị trộn với HTTP hoặc ORM khiến thay đổi khó kiểm soát.
- Một module có ranh giới dữ liệu và quyền sở hữu rõ, nhưng đang bị truy cập trực tiếp từ nhiều nơi.
- Tải hoặc rủi ro bảo mật đòi hỏi cô lập runtime.
- Tích hợp đồng bộ gây độ trễ hoặc làm một dependency lỗi kéo theo toàn bộ request.
- Chi phí vận hành của kiến trúc hiện tại thấp hơn hoặc cao hơn đáng kể so với nhu cầu thực tế.

Trước khi thêm tier, hãy kiểm tra liệu có thể giải quyết bằng cách cải thiện layer logic, query, cache, connection pool, async job hoặc scale replica của ứng dụng hiện tại hay không. Tách dịch vụ là một lựa chọn có tác động lớn, cần chứng minh lợi ích vượt chi phí giao tiếp và vận hành.

Không cần đợi hệ thống gặp sự cố mới tiến hóa. Có thể chuẩn bị hợp đồng, module boundary và test kiến trúc sớm để sau này dễ tách. Tuy nhiên, chuẩn bị khả năng thay đổi không có nghĩa phải triển khai phân tán ngay từ đầu.

## 10. Ghi quyết định và giới hạn kiến trúc

Một quyết định kiến trúc nên ghi rõ:

- Bối cảnh và yêu cầu thúc đẩy quyết định.
- Các phương án đã cân nhắc.
- Vì sao chọn số layer logic và số deployment tier hiện tại.
- Các đánh đổi về độ trễ, transaction, bảo mật và vận hành.
- Giả định cần được kiểm chứng.
- Chỉ số hoặc điều kiện khiến nhóm xem xét lại quyết định.

Ví dụ:

```text
Quyết định: Giữ Order trong một modular monolith
Layer logic: presentation, application, domain, infrastructure
Deployment: một backend deployable, database managed riêng
Lý do: Các luồng cần transaction chung; tải chưa cần scale riêng
Đánh đổi: Order và worker cùng release trong giai đoạn đầu
Điều kiện xem xét lại: Báo cáo làm ảnh hưởng latency API hoặc cần lịch phát hành riêng
Biện pháp: Giữ application contract và message boundary rõ; đo latency và tải worker
```

Đây là ví dụ quyết định, không phải mẫu kiến trúc bắt buộc. Khi điều kiện thay đổi, nhóm có thể tách worker hoặc một module thành service độc lập. Quyết định mới nên cập nhật các giả định và kế hoạch chuyển tiếp.

## 11. Kiểm thử và đo lường để xác minh lựa chọn

Kiến trúc không chỉ được đánh giá trên sơ đồ. Cần kiểm thử các ranh giới và đo các thuộc tính quan trọng.

- **Unit test:** xác minh domain rules và application policy.
- **Integration test:** kiểm tra adapter, repository, transaction và migration.
- **Contract test:** kiểm tra giao tiếp HTTP, message hoặc API giữa service.
- **Architecture test:** xác minh hướng phụ thuộc giữa package/module.
- **Load test:** đo throughput, latency và tài nguyên dưới workload đại diện.
- **Resilience test:** kiểm tra timeout, retry, circuit breaker và hành vi khi dependency lỗi.
- **Security test:** kiểm tra xác thực, phân quyền và vùng truy cập dữ liệu.

Nếu quyết định tách một tier để giảm latency, hãy đo latency trước và sau trên cùng loại workload. Nếu tách để scale độc lập, hãy kiểm tra tài nguyên và hiệu quả scale trong điều kiện tải thực tế. Nếu tách vì bảo mật, cần kiểm tra network policy, secret, identity và quyền truy cập thực tế.

Không dùng số lượng package, số lượng service hoặc coverage test như thước đo duy nhất cho chất lượng kiến trúc. Những số liệu đó có thể hữu ích trong ngữ cảnh cụ thể nhưng không chứng minh hệ thống đáp ứng yêu cầu.

## 12. Checklist chọn layer và tier

Trước khi quyết định cấu trúc, hãy trả lời:

1. Những trách nhiệm logic nào thực sự khác nhau về lý do thay đổi?
2. Các quy tắc nghiệp vụ có cần domain model riêng hay application service đơn giản đã đủ?
3. Những thành phần nào cần được triển khai, scale, release hoặc bảo mật độc lập?
4. Có cần transaction chung giữa các phần không? Nếu tách, dữ liệu sẽ nhất quán bằng cách nào?
5. Những lời gọi qua mạng thêm latency, timeout và failure mode nào?
6. Nhóm có năng lực vận hành thêm pipeline, runtime, monitoring, tracing và security boundary không?
7. Vấn đề hiện tại có thể giải quyết bằng cải thiện code, query, cache hoặc scale replica không?
8. Có thể giữ layer logic rõ trong một modular monolith trước khi tách tier không?
9. Các giả định và điều kiện xem xét lại quyết định đã được ghi nhận chưa?
10. Test và metrics nào sẽ chứng minh kiến trúc đang đáp ứng yêu cầu?

## 13. Ghi nhớ

- Layer mô tả trách nhiệm và hướng phụ thuộc logic; tier mô tả đơn vị triển khai hoặc môi trường thực thi.
- Nhiều layer có thể nằm trong một deployable; nhiều service/tier vẫn có thể có layer riêng bên trong.
- Folder, package và module Gradle không tự quyết định số layer hoặc tier.
- Chọn ranh giới logic theo quy tắc nghiệp vụ, hợp đồng và lý do thay đổi; chọn ranh giới triển khai theo nhu cầu scale, release, bảo mật, cô lập lỗi và vận hành.
- Tách tier tạo thêm giao tiếp mạng, latency, lỗi phân tán, yêu cầu bảo mật và chi phí vận hành.
- Modular monolith là lựa chọn hợp lệ khi cần ranh giới mã rõ nhưng chưa có nhu cầu triển khai độc lập.
- Không có số lượng layer hoặc tier tối ưu cho mọi hệ thống; quyết định phụ thuộc yêu cầu và đánh đổi cụ thể.
- Ghi lại bối cảnh, phương án, đánh đổi và điều kiện xem xét lại; dùng test và metrics để xác minh quyết định.

