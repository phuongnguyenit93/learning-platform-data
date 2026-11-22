# Kiến trúc phân lớp, N tầng và giới hạn của việc tách tầng

## Mục tiêu học tập

Trong thiết kế kiến trúc ứng dụng đám mây (**Cloud Architecture**), hai quyết định rất dễ bị nhầm lẫn là **chia trách nhiệm của mã nguồn thành các lớp** và **chia hệ thống chạy thành những tầng triển khai**. Kiến trúc phân lớp (*layered architecture*) giúp quản lý thay đổi, phụ thuộc và kiểm thử. Kiến trúc N tầng (*N-tier architecture*) xác định các ranh giới triển khai, kết nối mạng và năng lực vận hành. Một hệ thống có thể dùng nhiều lớp logic trong một tiến trình ứng dụng; ngược lại, một lớp có thể được triển khai trên nhiều tiến trình hoặc vùng hạ tầng.

Sau bài học, bạn có thể:

- Phân biệt *layer* (lớp logic) và *tier* (tầng triển khai), đồng thời phân biệt hai khái niệm này với module và microservice.
- Thiết kế các lớp presentation, application, domain và data/infrastructure với chiều phụ thuộc hợp lý.
- Ánh xạ cấu trúc ứng dụng Java/Spring Boot vào network, compute, database và mô hình triển khai trên cloud.
- Phân tích lợi ích, giới hạn và chi phí của việc tách tầng: bảo mật, mở rộng, cô lập sự cố, độ trễ mạng, dữ liệu và vận hành.
- Dựa vào yêu cầu nghiệp vụ, tiêu chí đo lường và nguyên tắc **Well-Architected** để quyết định số tầng phù hợp.

## 1. Bài toán thực tế: từ màn hình đặt chỗ đến kiến trúc cloud

Một nền tảng đặt chỗ cung cấp web, mobile app và API cho đối tác. Hệ thống cần tìm phòng, tính giá, đặt chỗ, thu tiền, hủy đặt chỗ và gửi thông báo. Nhóm nhận các yêu cầu:

- Quy tắc giá và điều kiện hủy phải giống nhau trên web, mobile và kênh đối tác.
- Khi lượng người tìm phòng tăng cao, API vẫn đạt độ trễ mục tiêu.
- Không bán cùng một chỗ hai lần khi có yêu cầu đồng thời hoặc retry.
- Người dùng chỉ được xem và sửa đặt chỗ của mình.
- Khi một instance hoặc một Availability Zone gặp sự cố, luồng đặt chỗ vẫn phục vụ được theo mục tiêu khôi phục đã chốt.
- Chi phí cloud và khối lượng công việc vận hành phải nằm trong ngân sách.

Hai loại câu hỏi kiến trúc xuất hiện:

1. **Mã nguồn được tổ chức thế nào?** Đâu là xử lý HTTP, điều phối use case, quy tắc nghiệp vụ, lưu trữ và gọi hệ thống bên ngoài?
2. **Thành phần chạy ở đâu?** Web, API, worker, database, cache nằm trong cùng tiến trình, những tiến trình khác nhau hay các subnet/cluster riêng? Có cần nhiều AZ/region không?

Câu hỏi thứ nhất dẫn tới **kiến trúc phân lớp**; câu hỏi thứ hai dẫn tới **N-tier và mô hình triển khai**. Không thể dùng số lượng thư mục Java để suy ra số lượng máy chủ.

## 2. Layer khác tier ở điểm nào?

### 2.1. Layer: ranh giới logic

Lớp logic gom các trách nhiệm có liên quan, đồng thời đặt ra quy tắc phụ thuộc và hợp đồng giữa chúng. Ví dụ:

| Lớp | Trách nhiệm | Ví dụ | Điều nên tránh |
| --- | --- | --- | --- |
| **Presentation / API** | Nhận request, kiểm tra định dạng đầu vào, chuyển DTO, trả response và mã lỗi | REST controller, input/output DTO | Nhúng SQL và chính sách tính giá trong controller |
| **Application / Use case** | Điều phối một ca sử dụng, xác định ranh giới transaction và kiểm tra quyền nghiệp vụ | CreateBookingService, CancelBookingUseCase | Gắn logic cốt lõi với HTTP servlet |
| **Domain / Business** | Bất biến, trạng thái, phép tính, chính sách và quy tắc nghiệp vụ | Booking, CancellationPolicy, PriceCalculator | Phụ thuộc vào cấu hình cloud hoặc driver cơ sở dữ liệu |
| **Infrastructure / Data access** | Triển khai lưu trữ, gọi dịch vụ ngoài, email, queue, object storage | JPA adapter, payment API client | Ra quyết định nghiệp vụ tùy tiện ở lớp tích hợp |

Một ứng dụng có thể chỉ dùng ba lớp presentation–business–data access. Nếu domain phức tạp, tách application và domain có thể giúp dễ kiểm thử và kiểm soát phụ thuộc. Không có một số lớp cố định bắt buộc cho mọi hệ thống.

### 2.2. Tier: ranh giới chạy hoặc triển khai

Tầng là nhóm thành phần được triển khai/thực thi ở một ranh giới riêng, thường tương tác với các tầng khác qua mạng. Một mô hình **3-tier** truyền thống có tầng trình bày, tầng ứng dụng và tầng dữ liệu.

| Thuật ngữ | Đối tượng phân chia | Ví dụ |
| --- | --- | --- |
| **Layer** | Trách nhiệm và dependency trong phần mềm | Controller → Service → Repository |
| **Tier** | Ranh giới triển khai, tiến trình, mạng | Web client → App server → Database server |
| **Module** | Ranh giới đóng gói và năng lực nghiệp vụ trong code | Booking, Payment, Inventory |
| **Service** | Thành phần cung cấp một hợp đồng chức năng, có thể nội bộ hoặc qua mạng | Booking service |
| **Microservice** | Dịch vụ có khả năng triển khai tương đối độc lập, thường gắn với năng lực nghiệp vụ và quyền quản lý dữ liệu | Payment service triển khai riêng |

Tên gọi *layer* và *tier* đôi khi được dùng đan xen trong tài liệu. Để tránh mơ hồ khi review, cần xác định rõ đang nói về **dependency trong code** hay **hành trình request qua mạng**.

### 2.3. Một hệ thống, hai sơ đồ đúng

Góc nhìn lớp logic:

~~~mermaid
flowchart TB
  API["Presentation: controller / DTO"]
  APP["Application: use case / transaction"]
  DOM["Domain: nghiệp vụ"]
  PORT["Repository interface"]
  ADAPTER["Persistence adapter: SQL / JPA"]
  API --> APP
  APP --> DOM
  APP --> PORT
  ADAPTER -. triển khai .-> PORT
~~~

Góc nhìn N-tier triển khai:

~~~mermaid
flowchart LR
  USER["Browser / Mobile"]
  EDGE["WAF / Load balancer"]
  A["App instance AZ A\nCác lớp logic"]
  B["App instance AZ B\nCác lớp logic"]
  DB[("Managed database")]
  USER --> EDGE
  EDGE --> A
  EDGE --> B
  A --> DB
  B --> DB
~~~

Dù có nhiều lớp code, các lớp đó **cùng nằm trong app instance**. Hạ tầng có tầng ứng dụng được nhân bản và tầng dữ liệu. Multi-AZ tăng khả năng chịu lỗi của một số thành phần, nhưng không tự động giải quyết lỗi ứng dụng hoặc dữ liệu bị xóa nhầm.

## 3. Nguyên tắc thiết kế kiến trúc phân lớp

### 3.1. Trách nhiệm và hợp đồng rõ ràng

Mỗi lớp nên cung cấp một hợp đồng dễ mô tả. Một luồng tạo booking có thể đi qua:

~~~text
HTTP POST /bookings
    → Controller: giải mã request, xác nhận định dạng
    → Application service: kiểm tra người gọi, điều phối use case, transaction
    → Domain: xác minh điều kiện nghiệp vụ
    → Repository port: yêu cầu ghi/truy vấn dữ liệu
    → Persistence adapter: câu lệnh SQL/JPA, ràng buộc dữ liệu
    → Application service: kết quả/exception
    → Controller: ánh xạ thành HTTP response
~~~

Với dữ liệu nhạy cảm, **ngữ cảnh xác thực** cần được lấy từ middleware/security context được server tin cậy, không dựa vào user ID do client tự gửi.

### 3.2. Strict layering và relaxed layering

- **Strict layering:** Một lớp chỉ gọi lớp liền kề theo quy tắc đã đặt. Dễ kiểm soát nhưng đôi khi thêm nhiều lớp chuyển tiếp không có giá trị.
- **Relaxed layering:** Có thể cho phép đường đọc đơn giản gọi một thành phần sâu hơn, với giới hạn rõ. Nếu không kiểm soát, các lớp dễ bị bỏ qua hoặc vô hiệu hóa.
- **Dependency inversion:** Domain/application định nghĩa giao diện cần sử dụng; adapter ở tầng ngoài triển khai giao diện đó. Luồng gọi lúc chạy có thể đi ra hạ tầng, nhưng phụ thuộc mã nguồn hướng về phía logic nghiệp vụ.

Đừng đồng nhất layering với việc tạo thật nhiều interface. Hợp đồng có ý nghĩa là hợp đồng giúp cách ly thay đổi, kiểm thử hoặc bảo vệ nghiệp vụ; interface chỉ có một triển khai không phải lỗi, nhưng cũng không tự chứng minh giá trị.

### 3.3. Đo tính kết dính và mức phụ thuộc

**Cohesion** nói về việc những phần mã cùng phục vụ một mục đích được đặt gần nhau. **Coupling** nói về mức độ một thay đổi làm phần khác phải sửa theo.

Nếu sửa giá phòng phải chỉnh controller, queue consumer, repository và ba dịch vụ chỉ để đồng bộ cùng một công thức, có khả năng quy tắc đang phân tán không đúng chỗ. Nếu một service chỉ ủy quyền một dòng sang repository, không mang hành vi hay kiểm soát nào, cũng nên cân nhắc liệu abstraction đó có cần thiết.

Một cấu trúc package theo tính năng cũng có thể kết hợp layering:

~~~text
com.example.booking
├── booking
│   ├── api
│   ├── application
│   ├── domain
│   └── infrastructure
├── catalog
│   ├── api
│   ├── application
│   └── infrastructure
└── payment
    ├── application
    └── infrastructure
~~~

Cách này giúp boundary giữa booking, catalog và payment rõ hơn so với đặt toàn bộ controller của mọi tính năng trong một package và toàn bộ service trong một package.

## 4. Ví dụ phân lớp với Java và Spring Boot

Giả sử ca sử dụng **xem chi tiết booking** chỉ được thực hiện bởi người có quyền trên booking. Những ví dụ dưới đây minh họa cấu trúc và ranh giới trách nhiệm; phần import, cấu hình bảo mật và ánh xạ exception HTTP được lược bỏ.

### 4.1. Domain và hợp đồng repository

~~~java
public record Booking(
    UUID id,
    UUID customerId,
    BookingStatus status
) {}

public enum BookingStatus {
    PENDING, CONFIRMED, CANCELLED
}

public interface BookingRepository {
    Optional<Booking> findById(UUID bookingId);
}
~~~

Trong thiết kế theo dependency inversion, giao diện repository có thể đặt ở lớp domain hoặc application, nơi định nghĩa **điều ứng dụng cần**. Lớp lưu trữ cụ thể chịu trách nhiệm triển khai.

### 4.2. Application service

~~~java
public final class BookingQueryService {
    private final BookingRepository repository;

    public BookingQueryService(BookingRepository repository) {
        this.repository = repository;
    }

    public Booking findForCustomer(UUID bookingId, UUID callerId) {
        Booking booking = repository.findById(bookingId)
            .orElseThrow(BookingNotFoundException::new);

        if (!booking.customerId().equals(callerId)) {
            throw new BookingAccessDeniedException();
        }

        return booking;
    }
}
~~~

Ở đây quyền xem được kiểm tra trong use case, nên nếu sau này thêm API mobile, batch hoặc GraphQL thì quy tắc vẫn được tái sử dụng. Trong sản phẩm thật, quy tắc quyền có thể phức tạp hơn và được tách thành policy chuyên dụng.

### 4.3. Controller và DTO

~~~java
public record BookingResponse(
    UUID id,
    UUID customerId,
    String status
) {}

@RestController
@RequestMapping("/bookings")
public class BookingController {
    private final BookingQueryService service;

    public BookingController(BookingQueryService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public BookingResponse get(
        @PathVariable UUID id,
        @AuthenticationPrincipal AppPrincipal principal
    ) {
        Booking booking = service.findForCustomer(
            id, principal.userId()
        );
        return new BookingResponse(
            booking.id(),
            booking.customerId(),
            booking.status().name()
        );
    }
}
~~~

Controller xử lý giao thức HTTP, còn quyết định về quyền truy cập nằm ở phía application. *AppPrincipal* phải được tạo từ quy trình xác thực đã kiểm chứng. API cần có cơ chế xử lý ngoại lệ và ánh xạ HTTP status nhất quán; ví dụ này chưa phải ứng dụng có thể chạy độc lập.

### 4.4. Persistence adapter

~~~java
@Component
public class BookingRepositoryAdapter implements BookingRepository {
    private final BookingJpaRepository jpa;

    public BookingRepositoryAdapter(BookingJpaRepository jpa) {
        this.jpa = jpa;
    }

    @Override
    public Optional<Booking> findById(UUID id) {
        return jpa.findById(id).map(entity ->
            new Booking(
                entity.getId(),
                entity.getCustomerId(),
                BookingStatus.valueOf(entity.getStatus())
            )
        );
    }
}
~~~

Adapter chuyển đổi giữa mô hình persistence và mô hình nghiệp vụ, giảm việc rò rỉ entity JPA ra HTTP và domain. Cần cân nhắc chi phí mapping thực tế; không nhất thiết tạo một lớp chuyển đổi cho mọi dữ liệu đơn giản.

**Ranh giới transaction:** Với use case tạo booking, transaction thường điều phối ở application service. Bất biến “một phòng không được bán hai lần” còn cần được bảo vệ bằng cơ chế đồng thời ở database, ví dụ unique constraint, optimistic/pessimistic lock hoặc update có điều kiện. Kiểm tra trong Java rồi mới ghi **không đủ** khi hai request chạy đồng thời.

## 5. Những mô hình triển khai từ đơn giản đến nhiều tầng

### 5.1. Một tiến trình ứng dụng và một database

~~~mermaid
flowchart LR
  C["Client"] --> APP["Spring Boot process\nController + Use case + Domain + Adapter"]
  APP --> DB[("Managed DB")]
~~~

Ứng dụng có nhiều layer nhưng cùng một deployable unit. Có thể tạo nhiều bản sao app sau load balancer cho khả năng mở rộng và độ tin cậy mà không cần biến các layer thành dịch vụ mạng riêng.

Mô hình này thường dễ phát triển, kiểm thử, triển khai và rollback; phù hợp khi nhóm nhỏ, nghiệp vụ gắn kết và SLO có thể đáp ứng bằng scale nhiều instance.

### 5.2. Ba tầng (3-tier)

~~~mermaid
flowchart LR
  WEB["Presentation tier\nWeb frontend"]
  APP["Application tier\nBusiness logic"]
  DATA[("Data tier\nDatabase")]
  WEB --> APP --> DATA
~~~

Ở mô hình truyền thống, presentation, application và data chạy ở ba ranh giới triển khai. Với SPA/mobile hiện đại, presentation có thể nằm ở browser, CDN hoặc frontend server. API gateway có thể bổ sung ranh giới triển khai và policy nhưng không nhất thiết tạo thêm lớp nghiệp vụ.

Ưu điểm là có thể mở rộng và bảo vệ web, app, DB theo đặc điểm riêng. Hệ quả là xuất hiện network hop, connection, timeout, logging xuyên tầng và trách nhiệm vận hành các thành phần mới.

### 5.3. N tầng với xử lý bất đồng bộ

~~~mermaid
flowchart TB
  U["Web / Mobile"] --> EDGE["CDN / WAF / API gateway"]
  EDGE --> API["Booking application"]
  API --> DB[("Transactional DB")]
  API --> QUEUE[("Message queue")]
  QUEUE --> WORKER["Notification worker"]
  API --> CACHE[("Cache, nếu cần")]
~~~

Worker và queue tạo một đường xử lý khác để tác vụ thông báo không nằm trên đường phản hồi booking nếu yêu cầu nghiệp vụ cho phép. Tuy nhiên, queue không tự đảm bảo sự kiện được xử lý đúng một lần; consumer phải xử lý retry/trùng và có thể cần dead-letter queue.

Tùy cách phân loại, sơ đồ này có nhiều thành phần triển khai hơn mô hình ba tầng nhưng không nhất thiết mỗi thành phần là một tầng theo nghĩa tuyến tính. N-tier là mô hình để hiểu ranh giới chạy và phụ thuộc, không phải cuộc thi đếm số hộp.

## 6. Lợi ích thực tế của việc tách tầng

### 6.1. Mở rộng theo loại tải

Tầng web có thể cần nhiều kết nối, tầng xử lý nghiệp vụ cần CPU, còn worker theo độ dài hàng đợi. Phân tách cho phép cấp tài nguyên theo tải thực tế, chẳng hạn scale worker khi backlog tăng mà không cần scale tất cả API instance.

Cần xác định **nút thắt thực sự** trước khi tách. Nếu thời gian chờ database do lock hoặc truy vấn thiếu index mới là nguyên nhân tăng latency, nhân đôi tầng API có thể làm tình hình xấu hơn do mở thêm kết nối.

### 6.2. Giới hạn đường truy cập và quyền

Có thể đặt database vào private subnet, cho phép kết nối chỉ từ application tier và không cho truy cập trực tiếp từ Internet. Edge áp dụng TLS, WAF, rate limit; ứng dụng kiểm tra quyền trên từng tài nguyên.

Tách network tier giúp đặt chính sách riêng, nhưng **không tự đảm bảo bảo mật**. Phải kiểm soát danh tính service-to-service, mã hóa khi truyền/lưu, quyền tối thiểu, audit và ranh giới dữ liệu nhạy cảm.

### 6.3. Cô lập lỗi

Nếu email gateway chậm, luồng booking có thể tiếp tục ghi thành công rồi phát sự kiện thông báo qua queue. Worker lỗi thì nhiệm vụ gửi thông báo bị chậm nhưng không nhất thiết ngăn đặt chỗ.

Ngược lại, nếu quy tắc đặt chỗ bị tách thành ba service đồng bộ bắt buộc, lỗi một service có thể làm thất bại cả request. Có thêm tiến trình riêng **không đồng nghĩa** có độ tin cậy end-to-end tốt hơn.

### 6.4. Vòng đời phát hành và ownership

Tách frontend, API và worker giúp triển khai riêng khi contract ổn định. Một nhóm có thể cập nhật frontend mà không phát hành backend.

Tuy nhiên, tính độc lập triển khai bị hạn chế nếu mọi thay đổi đều buộc sửa schema chung hoặc phát hành đồng thời nhiều service. Ranh giới dữ liệu, API versioning và backward compatibility quan trọng hơn số lượng pipeline.

## 7. Giới hạn và đánh đổi của việc tách tầng

### 7.1. Độ trễ mạng và rủi ro tải theo chuỗi

Lời gọi nội bộ JVM khác rất xa lời gọi HTTP/gRPC qua mạng. Mỗi hop có thể bổ sung:

- Độ trễ truyền mạng và load balancer.
- Serialization/deserialization, TLS, connection setup.
- Connection pool, DNS, quota và khả năng nghẽn.
- Timeout, retry, lỗi một phần hoặc kết quả không rõ.
- Chi phí network, egress và observability.

Ví dụ **minh họa**, ứng dụng xử lý logic hết trung bình 40 ms. Nếu có ba lời gọi **tuần tự** sang tầng khác, mỗi lời gọi thêm trung bình 12 ms thì ước lượng thời gian trung bình đơn giản là:

~~~text
40 ms + 3 × 12 ms = 76 ms
~~~

Đây **không phải** dự báo p95 hay p99. Percentile không thể cộng đơn giản từ giá trị trung bình; tail latency, retry và queueing còn có thể khiến thời gian thực cao hơn nhiều.

**Chatty architecture** là anti-pattern phổ biến: service A gọi B cho từng dòng dữ liệu, B lại gọi C cho mỗi thuộc tính. Với 100 bản ghi, luồng N+1 qua mạng có thể tạo hàng trăm round trip. Cân nhắc batch API, read model, truy vấn tổng hợp hoặc cache theo tính chất dữ liệu.

### 7.2. Nhiều phụ thuộc bắt buộc làm thay đổi độ sẵn sàng

Giả sử một hành trình người dùng phải gọi thành công ba service độc lập, mỗi service có xác suất thành công 99,9% trong khoảng đo đã định. Nếu **giả định lỗi độc lập** và cả ba đều bắt buộc, xác suất thành công đơn giản hóa là:

~~~text
0,999 × 0,999 × 0,999
= 0,997002999
≈ 99,7003%
~~~

Kết quả chỉ minh họa tác động của việc thêm phụ thuộc. Trong thực tế, lỗi có thể tương quan, có fallback/retry và SLO có thể đo theo cách khác. Nhưng không nên lấy uptime của từng service để suy ra một cách máy móc tính sẵn sàng của **toàn giao dịch đặt chỗ**.

### 7.3. Giao dịch phân tán

Một transaction ACID trong database **không tự mở rộng** sang hai database hoặc một dịch vụ thanh toán qua mạng. Khi booking, payment và inventory được tách thành dịch vụ độc lập, nhóm phải giải quyết trạng thái trung gian và xử lý thất bại.

| Cơ chế | Giá trị | Đánh đổi |
| --- | --- | --- |
| Transaction cùng DB | Giữ nhất quán mạnh trong một boundary | Không bao phủ mọi dịch vụ bên ngoài |
| Outbox + message broker | Kết nối trạng thái DB với việc phát sự kiện đáng tin cậy hơn | Cần relay, idempotency, retry, quan sát backlog |
| Saga/compensation | Điều phối chuỗi nghiệp vụ với bước xử lý bù | Phải mô hình hóa trạng thái trung gian, eventual consistency |
| Distributed transaction / 2PC | Có thể phối hợp nhất quán khi hệ thống hỗ trợ đầy đủ | Phức tạp, có thể ảnh hưởng độ sẵn sàng và không đồng nhất trên nhiều dịch vụ cloud |

Ví dụ, nếu thanh toán thành công nhưng client timeout, thao tác đặt lại có thể gây thu tiền hai lần nếu không có idempotency key và cơ chế đối soát. Việc tách payment thành một tier riêng không tự giải quyết vấn đề này.

### 7.4. Tăng chi phí vận hành và hạ tầng

Mỗi tier độc lập có thể yêu cầu compute, load balancer, địa chỉ/network, IAM, service account, cert, secret, logging, tracing, CI/CD, health check, alert, runbook và nguồn lực trực sự cố. Trên cloud còn có phí traffic qua AZ/region, NAT, egress hoặc private endpoint tùy kiến trúc.

Tổng chi phí cần tính theo **TCO**, gồm hạ tầng, dịch vụ managed, truyền dữ liệu, nhân sự, thử lỗi và chi phí thay đổi hệ thống. Hai phương án chỉ so sánh hợp lý khi phục vụ cùng nhu cầu và mục tiêu chất lượng.

### 7.5. Distributed monolith

Tách các lớp kỹ thuật thành service riêng nhưng dùng chung database/schema, phải phát hành đồng bộ và gọi nhau liên tục thường tạo thành **distributed monolith**: có gánh nặng mạng và triển khai phân tán nhưng vẫn bị khóa chặt khi thay đổi.

Dấu hiệu gồm:

- Sửa một quy tắc phải release hàng loạt service.
- Các service cùng thao tác vào bảng của nhau.
- Số lượng gọi đồng bộ liên tiếp lớn.
- Hệ thống không chạy/test riêng một module vì mọi thứ bắt buộc online.
- Một team duy nhất phải chăm sóc quá nhiều service nhỏ.

Giải pháp nên bắt đầu từ **đặt lại ranh giới nghiệp vụ và ownership dữ liệu**, thay vì tiếp tục nhân thêm service để giải quyết coupling.

## 8. Layered monolith, modular monolith, N-tier và microservices

Các mô hình sau có thể kết hợp chứ không hoàn toàn loại trừ nhau.

| Mô hình | Ý tưởng cốt lõi | Lợi ích | Giới hạn |
| --- | --- | --- | --- |
| **Layered monolith** | Nhiều lớp logic trong một deployable app | Đường gọi ngắn, transaction đơn giản, deploy dễ | Scale và release thường đi cùng |
| **Modular monolith** | Một deployable app, các module nghiệp vụ có boundary rõ | Dễ kiểm thử, ownership trong code, chuẩn bị tách sau | Chưa scale/release module độc lập nếu chỉ một tiến trình |
| **N-tier** | Các tầng triển khai có ranh giới network hoặc tiến trình | Tách security/scaling/availability theo tầng | Network hop, ops và chi phí tăng |
| **Microservices** | Các dịch vụ nghiệp vụ triển khai tương đối độc lập | Scaling, ownership và release độc lập khi boundary tốt | Distributed transaction, contract, observability khó hơn |

Ứng dụng microservices vẫn có thể dùng layer **bên trong mỗi service**. Ngược lại, một monolith phân lớp có thể được triển khai trên nhiều AZ với tính sẵn sàng cao. Các khái niệm trả lời những câu hỏi khác nhau.

**Lựa chọn thực tế:** Khi sản phẩm mới, team nhỏ và quy tắc nghiệp vụ thay đổi nhanh, modular monolith với ranh giới rõ thường dễ bắt đầu. Một module chỉ nên trở thành service riêng khi có nhu cầu độc lập về tải, release, ownership, bảo mật hoặc vòng đời dữ liệu đủ rõ để bù chi phí vận hành phân tán.

## 9. Thiết kế N-tier trên cloud theo network, compute, data và deployment

### 9.1. Network và bảo mật

~~~mermaid
flowchart TB
  CLIENT["Internet client"] --> WAF["WAF / Public load balancer"]
  subgraph CLOUD["Virtual private network - multi AZ"]
    subgraph APP["Private application subnets"]
      A["App A"]
      B["App B"]
    end
    subgraph DATA["Private data subnets"]
      DB[("Database")]
    end
    A --> DB
    B --> DB
  end
  WAF --> A
  WAF --> B
~~~

Các nguyên tắc thiết kế:

1. Chỉ công khai endpoint phải truy cập từ Internet; database thường không cần public IP.
2. Đặt rule mạng theo lưu lượng thực sự cần thiết, không cho phép mọi port chỉ vì dùng private subnet.
3. Xác thực service-to-service và mã hóa dữ liệu truyền qua các ranh giới quan trọng.
4. Xem xét phí và độ trễ traffic xuyên AZ/region khi thiết kế chatty path.
5. Xác định hành vi khi DNS, kết nối hoặc load balancer gặp lỗi; thử timeout và retry.

### 9.2. Compute và tự mở rộng

App stateless có thể chạy trên VM, container, managed application runtime hoặc serverless tùy yêu cầu. Nên cân nhắc cơ chế health check, shutdown graceful, xử lý session, autoscaling metric, quota, giới hạn concurrent requests và cold start nếu có.

Nếu API và batch scheduler dùng chung process, nhân bản API có thể nhân bản scheduler và tạo sự kiện trùng. Đây là ví dụ **tách worker** có giá trị rõ ngay cả khi vẫn chung codebase.

### 9.3. Data và tính nhất quán

Tầng dữ liệu cần:

- Định nghĩa ai sở hữu bảng/dữ liệu và bất biến nào phải được database bảo vệ.
- Thiết kế index, connection pool, cache invalidation, kiểm soát truy vấn N+1.
- Backup/restore đã diễn tập, RPO/RTO theo loại sự cố.
- Encryption, quyền truy cập và audit dữ liệu nhạy cảm.
- Dự báo lưu lượng, IOPS, storage growth và chi phí replication.

Đừng suy luận rằng “có tầng data” đồng nghĩa “mỗi lớp logic phải có database riêng”. Database riêng nên đi theo ranh giới dữ liệu, quyền sở hữu và yêu cầu độc lập thực sự.

### 9.4. Deployment và độ tin cậy

Multi-AZ có thể bảo vệ một phần rủi ro ở cấp AZ; multi-region có thể phục vụ DR khi region mất. Nhưng **backup khác failover**: đa AZ không thay thế bản sao lưu khỏi lỗi xóa nhầm hoặc ghi sai logic.

Mỗi kịch bản phải nêu rõ: khi instance, AZ, region, ứng dụng hoặc database lỗi thì phần nào tiếp tục chạy; RTO, RPO và cách đo thực tế. Việc tách nhiều tier làm xuất hiện thêm những phụ thuộc cần kiểm tra trong diễn tập.

## 10. Chọn ranh giới bằng kịch bản chất lượng có tiêu chí đo

Giả sử doanh nghiệp đặt các mục tiêu **minh họa** sau; con số cần được xác nhận với product owner và dữ liệu tải thực tế.

| Mã | Tác động và môi trường | Phản hồi mong đợi | Thước đo |
| --- | --- | --- | --- |
| QA-PERF-01 | Giờ cao điểm, tìm phòng đạt 800 req/s trong 30 phút | API giữ chất lượng và không làm nghẽn DB | p95 ≤ 400 ms; HTTP 5xx < 0,5% tại gateway |
| QA-REL-01 | Một AZ ứng dụng ngừng hoạt động | Load balancer chuyển lưu lượng tới instance còn hoạt động | ≥ 99,9% booking request hợp lệ thành công trong cửa sổ thử 15 phút |
| QA-SEC-01 | Tài khoản A truy cập booking của B | Từ chối ở phía server và ghi audit | 100% ca trong bộ kiểm thử phân quyền bị từ chối, không lộ dữ liệu |
| QA-OPS-01 | Email provider chậm 10 phút | Booking không bị chặn, thông báo vào queue và xử lý sau | Booking vẫn đạt SLO; queue age trở về dưới ngưỡng đã chốt |
| QA-REC-01 | Database mất dữ liệu hoặc không thể phục vụ | Restore và đối soát booking | RTO/RPO đã thống nhất, đo từ diễn tập end-to-end |
| QA-COST-01 | Lưu lượng tăng gấp ba | Scale đúng thành phần | Chi phí/booking hoàn tất dưới ngân sách đã chốt |

Những tiêu chí này gợi ra giải pháp khác nhau: với QA-OPS-01, tách worker/queue có lợi; với QA-REL-01, nhiều instance qua AZ có thể đủ; với QA-REC-01, cần backup và chiến lược phục hồi dữ liệu, không giải quyết bằng cách tạo thêm service.

**SLI** là chỉ số quan sát được, **SLO** là mục tiêu của chỉ số đó. **RTO** là giới hạn thời gian khôi phục; **RPO** là khoảng mất dữ liệu tối đa tính theo thời gian. Cả hai cần kiểm chứng bằng diễn tập chứ không suy ra từ tính năng hạ tầng đã bật.

### 10.1. Ma trận quyết định

| Tình huống | Phương án nên thử trước | Bằng chứng cần có |
| --- | --- | --- |
| Cùng nhóm phát triển, tải vừa, logic gắn kết | Modular monolith phân lớp | Unit/integration test, SLO và tốc độ release |
| Notification làm chậm booking | Queue và worker riêng | p95 booking, queue lag, retry, idempotency |
| Một nhóm nghiệp vụ có tải và release độc lập thực sự | Service riêng theo domain | API contract, data ownership, cost, load test |
| DB là nút thắt chính | Tối ưu query/index/connection, cache hoặc read model | Query plan, p95, DB saturation |
| Yêu cầu cách ly mạng dữ liệu nhạy cảm | Private network tier và policy | Security test, audit, đánh giá threat model |
| Microservices đã tách nhưng release đồng thời | Củng cố contract hoặc xem lại boundary | Số thay đổi liên service, test và thời gian release |

### 10.2. TCO minh họa

Giả sử phương án A là modular monolith với 2 app instances và DB, phương án B bổ sung service xử lý một use case nhỏ, load balancer nội bộ và worker riêng. Đơn vị **triệu VND/tháng**, chỉ minh họa bài học, không phải báo giá thực tế.

| Hạng mục | A: App phân lớp + DB | B: Nhiều tier/service |
| --- | ---: | ---: |
| Compute cho ứng dụng | 35 | 40 |
| Database và backup | 25 | 25 |
| Load balancer/network/egress | 8 | 15 |
| Queue và worker | 0 | 12 |
| Logging, tracing, monitoring | 7 | 12 |
| Công sức vận hành phân bổ | 20 | 35 |
| **Tổng** | **95** | **139** |

~~~text
Chênh lệch = 139 - 95 = 44 triệu VND/tháng
Tăng tương đối = 44 / 95 × 100% ≈ 46,3%
~~~

Mức tăng **chỉ phản ánh giả định**. Nếu B giúp loại bỏ nghẽn và giảm chi phí scale toàn hệ thống ở tải lớn, tổng chi phí có thể thay đổi. So sánh phải gồm **cùng SLO và khối lượng giao dịch**, chi phí mỗi booking hoàn tất, rủi ro sự cố và chi phí nhân lực, không chỉ giá VM theo giờ.

## 11. Case study: cải tiến nền tảng đặt chỗ theo bằng chứng

### 11.1. Ban đầu: phân lớp trong một ứng dụng

Booking, catalog, payment integration và notification được viết thành các module trong một Spring Boot application. Ứng dụng triển khai qua hai AZ sau load balancer, sử dụng managed PostgreSQL và backup.

Nhóm phát triển thuận lợi vì đường xử lý booking nằm chủ yếu trong một transaction, các module dễ kiểm thử và chỉ một artifact cần phát hành.

### 11.2. Vấn đề xuất hiện khi tăng tải

Load test ghi nhận ba hiện tượng giả định:

1. API tìm phòng tăng p95 do truy vấn filter thiếu index.
2. API tạo booking chờ email gửi đồng bộ, nên khi nhà cung cấp email chậm thì booking timeout.
3. Scheduler gửi thông báo chạy trong mỗi replica API, khiến nhân bản API tạo xử lý thông báo trùng.

Nếu chọn “tách tất cả các lớp Java thành microservices” sẽ có thêm nhiều hop mạng nhưng chưa chắc giải quyết nghẽn truy vấn và độ đúng đắn dữ liệu.

### 11.3. Phương án cải tiến có chủ đích

- Tối ưu query và index, giới hạn connection pool.
- Giữ transaction và quy tắc booking trong module nghiệp vụ hiện có.
- Lưu trạng thái booking và sự kiện cần gửi thông báo theo cách đáng tin cậy, ví dụ transactional outbox khi phù hợp.
- Đưa notification vào queue và worker riêng, xử lý idempotent, có retry có giới hạn và dead-letter queue.
- Chỉ cân nhắc tách catalog/search thành service riêng khi có nhu cầu về scaling, dữ liệu, ownership và release độc lập đã được chứng minh.

~~~mermaid
flowchart TB
  U["Web / Mobile"] --> LB["WAF / LB"]
  LB --> A["Spring Boot A: Booking + Catalog"]
  LB --> B["Spring Boot B: Booking + Catalog"]
  A --> DB[("Transactional DB")]
  B --> DB
  DB -. Outbox relay .-> Q[("Queue")]
  Q --> W["Notification worker"]
~~~

### 11.4. Kiểm chứng sau thay đổi

Thử lại với cùng tập dữ liệu và đường tăng tải ban đầu, thu thập:

- Booking success rate, p95/p99, HTTP 5xx và trường hợp timeout.
- Queue lag, số sự kiện lỗi, độ trễ gửi thông báo, số sự kiện xử lý trùng.
- DB latency, connection pool, lock wait và throughput.
- Kết quả tiêm lỗi instance/AZ và phục hồi.
- Tổng chi phí cloud, vận hành và chi phí mỗi booking thành công.

Nếu mục tiêu đo chưa đạt, nhóm điều chỉnh kiến trúc dựa trên nguyên nhân thực tế. Bản thân việc “đã tách worker” chưa đủ bằng chứng thành công.

## 12. Kiểm thử, observability và vận hành xuyên tầng

| Hạng mục | Câu hỏi kiểm chứng | Bằng chứng |
| --- | --- | --- |
| Unit test | Logic hủy/giá/phân quyền chạy mà không cần web/DB không? | Test application/domain |
| Integration test | Constraint DB, transaction và concurrent booking đúng không? | Test với database tương đương |
| Contract test | Frontend và backend còn tương thích giữa các bản phát hành không? | API schema và contract test |
| Load test | p95/p99 và throughput đạt ở tải mục tiêu không? | Dashboard theo cùng dữ liệu thử |
| Fault injection | Khi instance/AZ/queue/API phụ thuộc lỗi, luồng nào còn chạy? | Thời gian lỗi, tỷ lệ thành công, trace |
| Restore drill | Dữ liệu và dịch vụ được khôi phục đúng thời hạn không? | RTO/RPO thực đo và đối soát |
| Security test | Có chặn truy cập vượt quyền và log nhạy cảm không? | Bộ ca kiểm thử và audit event |

**Observability:** Nên kết hợp metrics (request rate/error rate/latency/saturation), logs có cấu trúc và distributed tracing khi có nhiều service. Correlation ID giúp nối đường đi của request; không nên log thông tin nhạy cảm để phục vụ truy vết.

**Timeout và retry:** Mỗi tầng có timeout nằm trong thời hạn tổng của request. Retry cần giới hạn, backoff với jitter và kiểm tra idempotency cho thao tác có side effect. Một client timeout **không có nghĩa** server chưa tạo booking; phải xử lý trường hợp phản hồi mất sau khi giao dịch đã được xác nhận.

**Triển khai:** Khi chạy nhiều phiên bản ứng dụng trong rolling/canary deployment, schema migration cần tương thích ngược đủ lâu để phiên bản cũ và mới cùng hoạt động.

## 13. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi khi phân lớp và tách tầng |
| --- | --- |
| **Operational Excellence** | Số thành phần có phù hợp năng lực deploy, trực sự cố, IaC, runbook và diễn tập không? |
| **Security** | Domain/data có được bảo vệ bởi least privilege, authentication/authorization, network segmentation và encryption không? |
| **Reliability** | Mỗi phụ thuộc đồng bộ làm thay đổi tỷ lệ thành công thế nào? Có failover, backup và kiểm chứng RTO/RPO không? |
| **Performance Efficiency** | Mỗi hop mạng có lợi ích đủ rõ? Đã đo p95/p99, throughput và độ nghẽn thực tế không? |
| **Cost Optimization** | Tách tier có giảm chi phí scale so với phần chi thêm cho compute, network, log và nhân lực không? |
| **Sustainability** | Có giảm overprovision và tránh truyền/nhân bản dữ liệu không cần thiết không? |

Đánh giá Well-Architected là quá trình rà soát các đánh đổi theo workload thực tế; không phải một mẫu sơ đồ cố định phải sao chép.

## 14. Mẫu ADR quyết định tách worker

~~~yaml
id: ADR-APP-002
title: Tach notification worker khoi Booking API
status: proposed
context:
  - Booking API cho email dong bo
  - p95 tang khi email provider cham
options:
  - synchronous_email
  - queue_and_worker
decision: queue_and_worker
quality_scenarios:
  - QA-PERF-01
  - QA-OPS-01
benefits:
  - Khong chan request booking vi email
  - Scale worker theo queue lag
risks:
  - Retry va xu ly trung
  - Can theo doi backlog, DLQ
verification:
  - TEST-BOOKING-LOAD
  - TEST-WORKER-RETRY
review_when:
  - SLO_khong_dat
  - Chi_phi_van_hanh_vuot_ngan_sach
owner: Architecture Team
~~~

Trong dự án thật, ADR nên có ngày, người chịu trách nhiệm, bằng chứng thử nghiệm và phương án rollback. Các ngưỡng và tên test trong mẫu chỉ minh họa cách truy vết quyết định.

## 15. Sai lầm thường gặp

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Có ba package nghĩa là phải có ba server | Tăng hạ tầng không cần thiết | Vẽ riêng sơ đồ logic và triển khai |
| Tạo một microservice cho mỗi lớp kỹ thuật | Chatty calls, coupling và distributed monolith | Tách theo năng lực nghiệp vụ, dữ liệu |
| Cho rằng nhiều tier luôn an toàn hơn | Tăng điểm cấu hình, IAM, secret và network | Xây threat model và policy theo từng ranh giới |
| Thêm API replica khi nghẽn DB | Tăng connection và lock contention | Profile DB, index/query trước |
| Transaction ở service đủ chống đặt chỗ trùng | Race condition giữa các request | Database constraint/locking và test đồng thời |
| Có queue thì chỉ xử lý sự kiện đúng một lần | Retry có thể tạo xử lý trùng | Idempotency và kiểm tra đối soát |
| Cộng trung bình các hop để đo p95 | Không xét tail latency và retry | Load test end-to-end |
| Có multi-AZ thì không cần backup | Xóa nhầm/lỗi logic vẫn ảnh hưởng dữ liệu | Backup/restore và DR drill |
| Tách container là triển khai độc lập | Chia sẻ schema và cần đồng release | Hợp đồng, migration tương thích và ownership dữ liệu |
| Kiến trúc phân lớp lỗi thời | Mất một công cụ tổ chức trách nhiệm hữu ích | Dùng layering trong monolith hoặc service nếu phù hợp |

## 16. Bài tập thực hành

Một công ty có hệ thống quản lý đơn hàng Java/Spring Boot. Lưu lượng bình thường 100 req/s, cao điểm 800 req/s. Nhóm 7 người vận hành dịch vụ tạo đơn, thanh toán, theo dõi vận chuyển và gửi email.

1. Vẽ kiến trúc **bốn lớp logic** cho ca sử dụng tạo đơn, giải thích quyền và transaction nằm ở đâu.
2. Vẽ hai cách triển khai: **A** là modular monolith phân lớp với database và worker; **B** tách order, payment và notification thành các service. Phân biệt số lớp logic và số tier vật lý.
3. Với ba lời gọi đồng bộ liên tiếp, mỗi lời gọi thêm trung bình 15 ms, tính phần thời gian trung bình bổ sung; giải thích vì sao chưa thể kết luận p95.
4. Xử lý trường hợp người dùng bấm thanh toán hai lần hoặc retry sau timeout; chỉ ra database constraint, idempotency và đối soát cần thiết.
5. Phác thảo cách kiểm thử khi mất một AZ và khi dịch vụ email lỗi 10 phút, với SLI, SLO và thước đo đạt/trượt.
6. Lập bảng TCO tháng cho hai phương án, bao gồm network, load balancer, database, queue, logging và vận hành.
7. Viết ADR một trang chọn phương án phù hợp với đội 7 người, nêu rủi ro và điều kiện cần xem xét lại.

**Gợi ý tự đánh giá:** Một phương án tốt giải thích được *tại sao* cần mỗi ranh giới, tác động đến chất lượng và **cách đo** hiệu quả sau thay đổi.

## 17. Checklist quyết định kiến trúc

- [ ] Đã phân biệt layer, tier, module và microservice.
- [ ] Mỗi lớp có trách nhiệm và hợp đồng rõ, quy tắc nghiệp vụ không nằm rải rác ở controller.
- [ ] Có quy tắc phụ thuộc hợp lý, kiểm thử được domain/application độc lập với adapter.
- [ ] Từng tầng triển khai mới có lý do về tải, bảo mật, ownership hoặc vòng đời thay đổi.
- [ ] Đã nhận diện mọi lời gọi đồng bộ bắt buộc trên critical path.
- [ ] Đã đo tác động của network hop, serialization, timeout và retry đến p95/p99.
- [ ] Ranh giới transaction, tính nhất quán, idempotency và concurrency được thiết kế cụ thể.
- [ ] Có mô hình lỗi ở instance/AZ/database và cách khôi phục dữ liệu.
- [ ] IAM, network segmentation, encryption và audit phù hợp.
- [ ] Có metrics, logs, tracing, alerts và runbook cho các tầng vận hành.
- [ ] TCO bao gồm hạ tầng, network, công cụ quan sát và nhân lực.
- [ ] Kết luận được ghi thành ADR với tiêu chí kiểm chứng và điều kiện xem xét lại.

**Kết luận:** Kiến trúc phân lớp giải quyết cách **tổ chức trách nhiệm và phụ thuộc**; N-tier giải quyết cách **triển khai và kết nối các thành phần**. Việc tách thêm tầng chỉ mang lại giá trị khi giúp đáp ứng mục tiêu về hiệu năng, độ tin cậy, bảo mật, mở rộng hay vận hành với chi phí chấp nhận được. Hãy bắt đầu từ yêu cầu nghiệp vụ, đo chất lượng theo kịch bản và kiểm chứng các đánh đổi theo nguyên tắc Well-Architected.
