# Lựa chọn và tiến hóa kiến trúc

## Phân biệt phân tầng nội bộ dịch vụ với phân chia microservices

Trong module `SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED` — **Học tổ chức phần mềm theo kiến trúc phân tầng** — cần phân biệt hai quyết định kiến trúc thường bị nhầm lẫn: tổ chức mã nguồn thành các tầng trách nhiệm bên trong một dịch vụ và chia hệ thống thành nhiều microservice có thể triển khai độc lập.

**Phân tầng** trả lời câu hỏi: mã nguồn bên trong một ứng dụng được chia theo trách nhiệm và được phép phụ thuộc vào nhau như thế nào? **Microservices** trả lời câu hỏi: hệ thống được chia thành những dịch vụ độc lập nào, mỗi dịch vụ sở hữu khả năng nghiệp vụ và vòng đời triển khai ra sao? Một microservice vẫn có thể được tổ chức thành các tầng presentation, application, domain và data access. Hai cách tổ chức nằm ở hai mức khác nhau và có thể được sử dụng cùng nhau.

Bài học này dùng ví dụ hệ thống bán hàng Java/Spring để phân biệt ranh giới logic với ranh giới triển khai, hiểu modular monolith, nhận diện lợi ích và chi phí của microservices, rồi lựa chọn cách tiến hóa phù hợp.

## 1. Hai câu hỏi kiến trúc ở hai mức khác nhau

### Phân tầng nội bộ một dịch vụ

Tầng là ranh giới **logic** trong mã nguồn. Mỗi tầng gom những trách nhiệm có liên quan và quy định hướng phụ thuộc. Một cấu trúc thường gặp:

| Tầng | Trách nhiệm | Ví dụ Java/Spring |
| --- | --- | --- |
| Presentation | Tiếp nhận giao tiếp bên ngoài và chuyển đổi request/response | REST controller, request DTO |
| Application | Điều phối ca sử dụng và ranh giới giao dịch | `PlaceOrderService`, command handler |
| Domain | Mô hình và quy tắc nghiệp vụ | `Order`, `Money`, domain policy |
| Data access / Infrastructure | Truy xuất dữ liệu và tích hợp công nghệ | JPA repository adapter, HTTP client |

Các tầng này thường nằm trong cùng một ứng dụng, cùng tiến trình và cùng đơn vị triển khai. Chúng có thể được tổ chức bằng package, Java module hoặc module build. Số tầng không cố định; dự án có thể gộp hoặc tách trách nhiệm tùy nhu cầu.

### Phân chia microservices

Microservices là cách chia hệ thống thành nhiều dịch vụ nhỏ hơn, mỗi dịch vụ sở hữu một khả năng nghiệp vụ hoặc một ranh giới miền tương đối độc lập. Mỗi dịch vụ có thể có mã nguồn, dữ liệu, quy trình triển khai, cấu hình vận hành và nhịp phát hành riêng. Các dịch vụ giao tiếp qua hợp đồng như HTTP API, gRPC hoặc message/event.

Ví dụ một hệ thống bán hàng có thể gồm:

- `Order Service`: tiếp nhận và quản lý vòng đời đơn hàng.
- `Inventory Service`: quản lý tồn kho và giữ chỗ hàng.
- `Payment Service`: quản lý giao dịch thanh toán và hoàn tiền.
- `Shipping Service`: quản lý vận chuyển và theo dõi giao hàng.

Mỗi service có thể chứa các tầng logic bên trong. `Order Service` có controller, application service, domain model và adapter dữ liệu của riêng nó; `Inventory Service` cũng có cấu trúc nội bộ phù hợp với trách nhiệm tồn kho.

## 2. Phân biệt tầng logic, tier triển khai và microservice

Ba khái niệm này mô tả những khía cạnh khác nhau:

| Khái niệm | Đơn vị được mô tả | Câu hỏi chính |
| --- | --- | --- |
| Layer (tầng logic) | Nhóm trách nhiệm và quy tắc phụ thuộc trong mã nguồn | Thành phần nào được phép gọi hoặc phụ thuộc vào thành phần nào? |
| Deployment tier (tầng triển khai) | Nơi hoặc tiến trình mà phần mềm chạy | Phần nào chạy trên máy chủ, tiến trình hoặc môi trường nào? |
| Microservice | Ranh giới dịch vụ và khả năng nghiệp vụ có thể triển khai độc lập | Khả năng nào có quyền sở hữu, dữ liệu và vòng đời phát hành riêng? |

Một ứng dụng Spring Boot dạng monolith có thể có bốn tầng logic nhưng chỉ một đơn vị triển khai ứng dụng. Cơ sở dữ liệu có thể chạy ở một tier khác. Khi tách hệ thống thành bốn microservice, mỗi service có thể tiếp tục có bốn tầng logic nội bộ. Vì vậy, không thể suy ra số microservice từ số tầng, cũng không nên triển khai mỗi tầng logic thành một dịch vụ mạng riêng.

Ví dụ không hợp lý thường gặp là tạo `Presentation Service`, `Business Service` và `Database Service` chỉ vì ứng dụng có ba tầng. Khi đó, mỗi request có thể phải đi qua mạng giữa các tầng, trong khi chúng vẫn cùng thực hiện một khả năng nghiệp vụ và không sở hữu dữ liệu hay vòng đời độc lập. Cách chia này thường tạo ra một hệ thống phân tán theo cấu trúc kỹ thuật, không phải theo năng lực nghiệp vụ.

## 3. Ví dụ: phân tầng bên trong một modular monolith

Một lựa chọn phù hợp cho nhiều hệ thống là **modular monolith**: ứng dụng được triển khai như một đơn vị, nhưng mã nguồn được chia thành các module nghiệp vụ có API nội bộ và quy tắc phụ thuộc rõ ràng.

Ví dụ cấu trúc Gradle hoặc package ở mức khái niệm:

```text
shop-app/
├── bootstrap/
│   └── ShopApplication.java
├── order/
│   ├── api/                 # hợp đồng nội bộ công khai
│   ├── application/         # use case của đơn hàng
│   ├── domain/              # Order, OrderPolicy
│   └── infrastructure/     # JPA adapter, messaging adapter
├── inventory/
│   ├── api/
│   ├── application/
│   ├── domain/
│   └── infrastructure/
└── payment/
    ├── api/
    ├── application/
    ├── domain/
    └── infrastructure/
```

Các module có thể giao tiếp qua API nội bộ hoặc interface/port. Ví dụ, `order.application` yêu cầu giữ chỗ thông qua `InventoryPort`; implementation nằm trong adapter tương ứng. Trong modular monolith, lời gọi có thể là lời gọi Java trực tiếp trong cùng JVM, nhưng vẫn cần tuân thủ ranh giới module.

```java
// Hợp đồng được module order sử dụng
public interface InventoryPort {
    ReservationResult reserve(ReservationRequest request);
}
```

```java
@Service
class PlaceOrderService {
    private final InventoryPort inventory;
    private final OrderRepository orders;

    PlaceOrderService(InventoryPort inventory, OrderRepository orders) {
        this.inventory = inventory;
        this.orders = orders;
    }

    @Transactional
    public void handle(PlaceOrderCommand command) {
        // Áp dụng quy tắc miền và điều phối ca sử dụng.
        // Gọi InventoryPort theo hợp đồng nội bộ.
        // Lưu đơn hàng; phần thân được lược bỏ trong ví dụ.
    }
}
```

Đoạn mã minh họa vị trí của hợp đồng, không phải triển khai hoàn chỉnh. Trong monolith, các module có thể dùng chung một database vật lý, nhưng nên quy định module nào sở hữu bảng hoặc aggregate nào. Việc dùng chung database không có nghĩa mọi module được phép truy vấn và cập nhật trực tiếp bảng của nhau.

Modular monolith giúp nhóm giữ ranh giới rõ ràng mà chưa phải vận hành giao tiếp mạng, khám phá dịch vụ, triển khai phân tán hoặc xử lý lỗi liên dịch vụ. Nếu sau này một module cần triển khai độc lập, hợp đồng và quyền sở hữu dữ liệu đã rõ sẽ giúp việc trích xuất dễ kiểm soát hơn.

## 4. Một microservice cũng cần phân tầng nội bộ

Khi `Inventory` được tách thành một microservice, ranh giới giao tiếp thay đổi từ lời gọi Java nội bộ sang API hoặc message. Nhưng bên trong `Inventory Service`, vẫn cần tổ chức trách nhiệm:

```text
Inventory Service (một đơn vị triển khai độc lập)
├── presentation
│   └── InventoryController / MessageConsumer
├── application
│   └── ReserveStockService
├── domain
│   └── StockItem / ReservationPolicy
└── infrastructure
    ├── JpaInventoryRepository
    └── EventPublisher
```

Luồng gọi có thể là:

```text
Order Service
    |
    | HTTP/gRPC hoặc command message
    v
Inventory Service
    |
    v
Controller / Consumer
    |
    v
ReserveStockService
    |
    v
StockItem + ReservationPolicy
    |
    v
Repository Adapter
    |
    v
Inventory Database
```

Tầng presentation của Inventory nhận giao thức; application điều phối use case giữ chỗ; domain bảo vệ bất biến tồn kho; adapter lưu trạng thái. Các tầng vẫn là cấu trúc logic trong một service. Việc service được triển khai độc lập không loại bỏ nhu cầu phân tầng.

## 5. Những khác biệt thực tế khi chuyển từ lời gọi nội bộ sang microservices

| Khía cạnh | Module trong cùng monolith | Microservices |
| --- | --- | --- |
| Giao tiếp | Lời gọi trong cùng tiến trình, interface hoặc event nội bộ | HTTP/gRPC/message qua mạng |
| Triển khai | Thường phát hành cùng ứng dụng | Có thể build, triển khai và rollback độc lập |
| Dữ liệu | Có thể dùng chung database vật lý, nhưng nên có quyền sở hữu module | Mỗi service thường sở hữu dữ liệu và schema của mình; service khác truy cập qua hợp đồng |
| Transaction | Có thể dùng một transaction database cho nhiều module nếu cùng transaction manager và nguồn dữ liệu | Transaction cục bộ của từng service; phối hợp liên dịch vụ cần saga/outbox hoặc cơ chế tương ứng |
| Lỗi | Exception và lỗi trong tiến trình | Timeout, mất kết nối, retry, lỗi một phần và kết quả không chắc chắn |
| Quan sát | Có thể theo dõi trong một tiến trình | Cần correlation ID, distributed tracing, log tập trung và metrics liên dịch vụ |
| Bảo mật | Có thể dựa vào ranh giới nội bộ và quyền trong ứng dụng | Cần xác thực và phân quyền giữa service, bảo vệ API và secret |
| Vận hành | Ít thành phần cần triển khai và giám sát | Nhiều pipeline, cấu hình, dashboard, cảnh báo và quy trình xử lý sự cố |

Khi chuyển sang microservices, một lời gọi phương thức nhanh và có thể thất bại theo kiểu exception trở thành lời gọi mạng có độ trễ, timeout và khả năng kết quả không rõ ràng. Nếu client gửi request, server xử lý thành công nhưng response bị mất, client không thể biết chắc thao tác đã hoàn tất hay chưa. Vì vậy, hợp đồng API cần có quy tắc idempotency, mã lỗi và cách retry rõ ràng.

### Quyền sở hữu dữ liệu

Một service nên là nơi chịu trách nhiệm thay đổi dữ liệu mà nó sở hữu. Nếu `Order Service` và `Payment Service` cùng ghi trực tiếp các bảng của nhau, schema database trở thành hợp đồng ngầm và hai service không thể tiến hóa độc lập.

Service khác cần thông tin thì dùng API, event hoặc read model được thiết kế rõ. Việc mỗi service sở hữu database riêng không nhất thiết có nghĩa phải dùng một máy chủ database riêng; điều quan trọng là quyền truy cập và thay đổi dữ liệu được kiểm soát qua ranh giới dịch vụ.

### Tính nhất quán và quy trình nhiều dịch vụ

Trong monolith, một transaction có thể cập nhật đơn và tồn kho trong cùng database nếu các thao tác cùng tham gia một transaction. Sau khi tách, mỗi service thường có transaction cục bộ. Không thể giả định `@Transactional` ở `Order Service` sẽ rollback được transaction đã commit ở `Inventory Service`.

Một quy trình đặt hàng phân tán có thể dùng saga: Order tạo trạng thái chờ; Inventory giữ chỗ; Payment xác nhận thanh toán; Order chuyển sang trạng thái xác nhận. Nếu thanh toán thất bại, quy trình phát lệnh giải phóng tồn kho hoặc thực hiện thao tác bù trừ tương ứng. Cần thiết kế idempotency, timeout, retry, trạng thái trung gian và khả năng xử lý message trùng.

## 6. Khi nào nên giữ phân tầng trong một dịch vụ?

Một monolith được phân tầng và chia module rõ ràng thường là lựa chọn hợp lý khi:

- Nhóm còn nhỏ hoặc chưa cần nhiều nhóm phát hành độc lập.
- Các phần nghiệp vụ thường thay đổi cùng nhau hoặc cần transaction xuyên qua nhiều phần dữ liệu.
- Lưu lượng và nhu cầu mở rộng chưa đòi hỏi scale độc lập từng khả năng.
- Hệ thống cần ưu tiên đơn giản hóa triển khai, debug và vận hành.
- Ranh giới nghiệp vụ chưa đủ ổn định để tách thành hợp đồng mạng.
- Nhóm chưa có khả năng vận hành tracing, monitoring, CI/CD, bảo mật service-to-service và xử lý lỗi phân tán.

Giữ monolith không có nghĩa là chấp nhận một codebase rối. Có thể tăng chất lượng bằng cách tạo module theo năng lực nghiệp vụ, giới hạn API nội bộ, kiểm tra hướng phụ thuộc và đặt quyền sở hữu dữ liệu. Một monolith được modular hóa tốt có thể phục vụ lâu dài.

## 7. Khi nào microservices có thể phù hợp?

Microservices có thể đem lại giá trị khi có nhu cầu thực tế về tính độc lập:

- Một khả năng nghiệp vụ có nhịp phát hành và đội ngũ sở hữu riêng.
- Tải hoặc yêu cầu mở rộng của một phần khác biệt đáng kể so với phần còn lại.
- Một phần cần cô lập lỗi, giới hạn tài nguyên hoặc yêu cầu bảo mật/vận hành riêng.
- Ranh giới miền và quyền sở hữu dữ liệu đã đủ rõ để service có thể hoạt động mà không truy cập trực tiếp dữ liệu nội bộ của service khác.
- Tổ chức có nền tảng tự động triển khai, quan sát hệ thống, quản lý cấu hình/secret và xử lý sự cố phân tán.

Không nên tách chỉ vì class quá lớn, package khó đọc hoặc muốn dùng công nghệ khác. Những vấn đề đó thường có thể giải quyết trước bằng phân tầng, refactor service, chia module và xác định hợp đồng nội bộ. Microservices không tự động sửa được domain model yếu hoặc trách nhiệm không rõ; chúng có thể làm vấn đề khó thay đổi hơn vì mỗi ranh giới nay có thêm mạng và dữ liệu phân tán.

## 8. Nhận diện distributed monolith và chia dịch vụ sai ranh giới

Một hệ thống có nhiều process chưa chắc đã có lợi ích của microservices. Các dấu hiệu sau cho thấy hệ thống có thể đang trở thành **distributed monolith**:

- Mọi thay đổi nhỏ đều yêu cầu triển khai nhiều service cùng lúc.
- Các service gọi đồng bộ lẫn nhau qua chuỗi dài để hoàn tất một request.
- Nhiều service cùng đọc/ghi một schema hoặc database mà không có quyền sở hữu rõ.
- Một service không thể chạy hoặc kiểm thử nếu phải khởi động nhiều service khác.
- Hợp đồng thay đổi thường xuyên và không có quy tắc tương thích phiên bản.
- Một lỗi hoặc sự cố ở service phụ làm hỏng toàn bộ luồng nghiệp vụ do không có timeout, fallback hoặc thiết kế suy giảm phù hợp.

Một cách chia theo tầng kỹ thuật cũng dễ tạo vấn đề: `Controller Service` gọi `Business Logic Service`, rồi `Database Service`. Khi đó, các service không sở hữu khả năng nghiệp vụ riêng; chúng chỉ là các phần của cùng một request bị đặt ở những process khác nhau. Độ trễ, vận hành và lỗi phân tán tăng lên mà tính độc lập không tăng tương ứng.

Hãy chia theo ranh giới nghiệp vụ và quyền sở hữu, không chia theo loại class hoặc tầng kỹ thuật. Một service có thể có nhiều tầng nội bộ; một tầng logic không cần trở thành service độc lập.

## 9. Tiến hóa từ monolith phân tầng sang microservices

Nếu có nhu cầu tách dịch vụ, hãy tiến hóa từng bước thay vì viết lại toàn bộ hệ thống:

1. **Làm rõ module nghiệp vụ:** nhóm mã theo năng lực như Order, Inventory, Payment; xác định API nội bộ và quy tắc phụ thuộc.
2. **Giới hạn truy cập dữ liệu:** xác định module sở hữu bảng/aggregate nào; thay truy cập trực tiếp bằng port hoặc API nội bộ.
3. **Tách hợp đồng khỏi implementation:** định nghĩa command, query, API hoặc event có ý nghĩa nghiệp vụ; không để kiểu JPA hoặc class nội bộ trở thành hợp đồng.
4. **Đo lường nhu cầu độc lập:** xác nhận service nào thực sự cần phát hành, scale, bảo mật hoặc cô lập lỗi riêng.
5. **Chọn một ranh giới tương đối độc lập:** ưu tiên phần có dữ liệu và vòng đời rõ, ít phụ thuộc đồng bộ hai chiều.
6. **Thiết kế giao tiếp phân tán:** xác định timeout, retry, idempotency, versioning, xác thực, observability và cách xử lý lỗi.
7. **Di chuyển dữ liệu có kiểm soát:** chuyển quyền ghi về service mới, đồng bộ dữ liệu cần thiết và xác định cách xử lý trong giai đoạn chuyển tiếp.
8. **Tách triển khai và quan sát:** triển khai độc lập, theo dõi luồng request bằng correlation ID/trace và xác minh hành vi trước khi mở rộng cách chia.

Mô hình Strangler có thể giúp chuyển dần: một số request được định tuyến sang service mới trong khi phần còn lại vẫn chạy trong monolith. Trong giai đoạn này cần tránh hai nơi cùng là nguồn dữ liệu chuẩn cho cùng một nghiệp vụ. Hãy xác định rõ quyền ghi, đồng bộ và kế hoạch ngừng đường cũ.

## 10. Khung quyết định lựa chọn

| Câu hỏi | Nghiêng về monolith phân tầng | Nghiêng về microservices |
| --- | --- | --- |
| Các phần có cần phát hành độc lập không? | Không hoặc hiếm khi | Có nhu cầu thường xuyên, có lý do rõ |
| Quyền sở hữu dữ liệu đã tách được chưa? | Dữ liệu còn cần transaction chung hoặc ranh giới chưa ổn định | Mỗi khả năng có dữ liệu và API sở hữu rõ |
| Có cần scale/cô lập tài nguyên độc lập không? | Tải tương đối đồng đều | Một số khả năng có tải hoặc yêu cầu riêng biệt |
| Năng lực vận hành phân tán đã sẵn sàng chưa? | Chưa; ưu tiên một pipeline và một runtime | Có CI/CD, tracing, monitoring, bảo mật và quy trình xử lý sự cố |
| Giao tiếp giữa phần nghiệp vụ có thể bất đồng bộ hoặc qua hợp đồng ổn định không? | Cần lời gọi trực tiếp và transaction chung | Có thể chấp nhận latency, lỗi mạng và tính nhất quán cuối cùng phù hợp |

Không có một điểm số hoặc số lượng service tối ưu áp dụng cho mọi tổ chức. Hãy cân nhắc chi phí sở hữu toàn vòng đời: phát triển, kiểm thử, triển khai, quan sát, bảo mật, xử lý sự cố và thay đổi hợp đồng. Nếu lợi ích độc lập chưa bù được chi phí phân tán, tiếp tục modular hóa monolith thường là quyết định tốt.

## Tự kiểm tra

1. Một ứng dụng Spring Boot có bốn tầng logic nhưng được triển khai thành một artifact có phải là microservice không? Vì sao?
2. Khi tách `Inventory` thành microservice, những tầng logic nào vẫn cần tồn tại bên trong service đó?
3. Vì sao chia `Presentation Service`, `Business Service` và `Database Service` thường không tạo ra ranh giới microservice tốt?
4. Quyền sở hữu dữ liệu thay đổi thế nào khi một module trong monolith được tách thành microservice?
5. Vì sao transaction cục bộ của hai microservice không thể mặc nhiên thay thế một transaction database chung?
6. Những dấu hiệu nào cho thấy một hệ thống nhiều service đang trở thành distributed monolith?
7. Trước khi tách một module thành microservice, nhóm nên làm rõ những ranh giới và năng lực vận hành nào?

