# Khảo sát đồ thị phụ thuộc, luồng xử lý và ranh giới đang trộn lẫn

Trong chương **Cải tiến hệ thống hiện có**, bài học này hướng dẫn cách tìm hiểu cấu trúc thực tế của một ứng dụng trước khi thay đổi kiến trúc. Với module **SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED**, mục tiêu là học tổ chức phần mềm theo kiến trúc phân tầng: nhận diện trách nhiệm trình bày, điều phối ứng dụng, nghiệp vụ và truy cập dữ liệu; hiểu hướng phụ thuộc; rồi xác định những nơi trách nhiệm đang bị trộn lẫn.

Trong hệ thống đã phát triển nhiều năm, sơ đồ kiến trúc ban đầu thường không còn phản ánh đầy đủ mã nguồn hiện tại. Một controller có thể vừa đọc HTTP request, vừa kiểm tra quyền, tính giá, ghi SQL và gửi email. Một service có thể gọi repository, đọc trực tiếp `HttpServletRequest`, cập nhật cache và phát message. Tên package có thể gợi ý tầng, nhưng chưa chứng minh trách nhiệm thật sự nằm ở đó. Trước khi tách lớp hoặc di chuyển package, cần khảo sát cách hệ thống thực sự hoạt động.

Khảo sát tốt kết hợp **đồ thị phụ thuộc**, **luồng xử lý thực tế** và **ranh giới trách nhiệm**. Đồ thị cho biết thành phần nào biết và gọi thành phần nào; luồng xử lý cho biết một yêu cầu đi qua đâu và tạo ra tác dụng phụ gì; phân tích ranh giới cho biết mỗi quyết định thuộc tầng nào. Ba góc nhìn này bổ sung cho nhau. Chỉ nhìn dependency graph có thể bỏ lỡ truy vấn động hoặc lời gọi qua framework; chỉ đọc một endpoint có thể bỏ lỡ các consumer khác đang dùng chung service; chỉ nhìn tên lớp có thể nhầm lẫn giữa vai trò được đặt tên và vai trò thực tế.

Sau bài học, bạn có thể:

- Phân biệt đồ thị phụ thuộc tĩnh, lời gọi lúc chạy và luồng dữ liệu/tác dụng phụ.
- Lần theo một ca sử dụng từ điểm vào đến nơi đọc/ghi dữ liệu và các hệ thống ngoài.
- Phân loại trách nhiệm trình bày, ứng dụng, nghiệp vụ và truy cập dữ liệu trong mã nguồn hiện hữu.
- Nhận diện dependency vòng, truy cập xuyên tầng, mô hình dữ liệu bị lộ và trách nhiệm trùng lặp.
- Thu thập bằng chứng bằng đọc mã, công cụ phân tích, log, trace và kiểm thử.
- Tạo bản đồ hiện trạng đủ tin cậy để chọn phạm vi refactor nhỏ và an toàn.

## 1. Vì sao phải khảo sát trước khi refactor?

Refactor kiến trúc tác động đến quan hệ giữa nhiều thành phần. Nếu chỉ nhìn một lớp rồi chuyển nó sang package khác, có thể bỏ sót những nơi đang gọi trực tiếp, những job chạy nền, message consumer hoặc truy vấn báo cáo dùng chung dữ liệu.

Ví dụ, nhóm thấy `OrderController` chứa một truy vấn SQL và muốn chuyển nó sang `OrderRepository`. Việc chuyển câu SQL có thể làm mã nguồn gọn hơn, nhưng chưa giải quyết được vấn đề nếu controller còn tự tính giảm giá, kiểm tra quyền và gửi email; đồng thời một batch job khác vẫn cập nhật bảng `orders` mà không qua quy tắc nghiệp vụ. Cần biết toàn bộ luồng và các điểm cùng tác động đến dữ liệu trước khi xác định ranh giới nên thay đổi.

Khảo sát giúp trả lời các câu hỏi nền tảng:

- Hệ thống có những điểm vào nào: HTTP, CLI, scheduler, message consumer, batch hay giao diện nội bộ?
- Một ca sử dụng đi qua các thành phần nào và phụ thuộc vào công nghệ nào?
- Thành phần nào chứa quy tắc nghiệp vụ và thành phần nào chỉ chuyển đổi dữ liệu?
- Ai sở hữu dữ liệu, ai đọc/ghi nó và có bao nhiêu đường cập nhật?
- Có dependency vòng, gọi xuyên tầng, truy cập trực tiếp hoặc tác dụng phụ ẩn nào không?
- Hành vi nào đang được bảo vệ bởi test và hành vi nào chưa có bằng chứng?

Mục tiêu của khảo sát không phải tạo một sơ đồ thật đẹp hoặc lập danh sách mọi lớp trong repository. Mục tiêu là hiểu các đường đi quan trọng và những ranh giới đang ảnh hưởng đến khả năng thay đổi, độ tin cậy và vận hành.

## 2. Ba góc nhìn cần khảo sát

### Đồ thị phụ thuộc tĩnh

Đồ thị tĩnh thể hiện quan hệ mà mã nguồn khai báo hoặc có thể phân tích: module import module, lớp tham chiếu kiểu khác, constructor nhận interface, lớp kế thừa, annotation hoặc cấu hình kết nối bean. Nó giúp phát hiện:

- Module trình bày phụ thuộc trực tiếp vào package persistence.
- Domain model import Spring Web hoặc JPA dù không cần biết framework.
- Hai package phụ thuộc lẫn nhau tạo thành chu trình.
- Một module dùng quá nhiều chi tiết nội bộ của module khác.
- Interface được khai báo nhưng consumer vẫn phụ thuộc vào lớp triển khai cụ thể.

Đồ thị tĩnh không nhất thiết cho thấy mọi lời gọi lúc chạy. Reflection, dependency injection, proxy, cấu hình bên ngoài, service loader hoặc tên lớp được nạp động có thể làm quan hệ thực tế khác với quan hệ nhìn thấy qua import.

### Đồ thị lời gọi lúc chạy

Call graph lúc chạy cho biết một thao tác cụ thể đã đi qua những method hoặc thành phần nào. Trace, log có correlation ID, profiler và breakpoint có thể giúp lần theo:

- Request đi từ controller đến use case nào.
- Service gọi repository hoặc dịch vụ ngoài theo thứ tự nào.
- Một method có tạo nhiều truy vấn hoặc gọi lại chính nó qua callback/proxy không.
- Transaction bắt đầu và kết thúc ở đâu.
- Lỗi, retry, event hoặc tác vụ bất đồng bộ phát sinh ở bước nào.

Call graph phụ thuộc vào kịch bản và dữ liệu chạy. Một trace của request thành công không thể đại diện cho mọi nhánh lỗi, job nền hoặc consumer khác. Cần khảo sát các kịch bản quan trọng, đặc biệt cả thành công, thất bại và retry.

### Luồng dữ liệu và tác dụng phụ

Một luồng xử lý không chỉ là chuỗi lời gọi. Cần ghi nhận dữ liệu nào được đọc, biến đổi và ghi; trạng thái nào thay đổi; message nào được phát; tài nguyên ngoài nào được gọi. Ví dụ, `approveOrder()` có thể:

- Đọc đơn hàng và quyền của actor.
- Kiểm tra trạng thái và quy tắc phê duyệt.
- Cập nhật trạng thái trong database.
- Ghi audit.
- Phát sự kiện `OrderApproved`.
- Gửi email hoặc tạo notification.

Nếu chỉ nhìn call graph mà không ghi tác dụng phụ, có thể chuyển method sang lớp khác nhưng làm thay đổi transaction, thứ tự ghi, thời điểm phát event hoặc chính sách retry.

## 3. Xác định phạm vi khảo sát

Không nên bắt đầu bằng việc đọc toàn bộ repository theo thứ tự thư mục. Chọn một lát cắt dọc (vertical slice) có ý nghĩa với người dùng hoặc vận hành, rồi mở rộng theo các dependency được phát hiện.

Một phạm vi tốt thường có:

1. **Điểm vào rõ ràng:** endpoint, command, message hoặc job cụ thể.
2. **Hành vi có giá trị:** tạo đơn, phê duyệt, thanh toán, tra cứu hoặc nhập dữ liệu.
3. **Dữ liệu và tác dụng phụ:** bảng được đọc/ghi, event phát ra, hệ thống ngoài được gọi.
4. **Consumer liên quan:** những adapter hoặc module khác cũng dùng chung thành phần.
5. **Rủi ro có thể kiểm chứng:** lỗi thường gặp, hiệu năng, dữ liệu không nhất quán hoặc thay đổi khó khăn.

Ví dụ, khảo sát `POST /orders` có thể bắt đầu từ `OrderController`, theo đến `OrderService`, repository, database và message publisher. Khi phát hiện `OrderService` còn được gọi từ `OrderImportJob`, hãy thêm job đó vào phạm vi vì nó là một consumer khác của cùng hành vi. Không cần mở rộng sang mọi module chỉ vì chúng cùng nằm trong một package cha.

Hãy xác định câu hỏi khảo sát trước. Nếu vấn đề là thay đổi quy tắc tính giá khó khăn, tập trung vào luồng tạo đơn và các nơi tính giá. Nếu vấn đề là dữ liệu bị cập nhật không nhất quán, tập trung vào mọi đường ghi của aggregate/bảng liên quan. Nếu vấn đề là một module không thể tách triển khai, khảo sát dependency giữa module và các điểm chia sẻ dữ liệu.

## 4. Lập bản đồ các điểm vào

Liệt kê những cách hệ thống bắt đầu một hành vi. Đây là bước dễ bị bỏ qua khi chỉ khảo sát web controller.

| Điểm vào | Ví dụ Java/Spring | Câu hỏi cần ghi nhận |
|---|---|---|
| HTTP | `@RestController`, filter, interceptor | Endpoint nào, xác thực ở đâu, DTO nào được nhận/trả? |
| CLI | `CommandLineRunner`, Spring Shell, picocli | Ai được chạy lệnh, tham số nào, exit code và log ra sao? |
| Scheduler | `@Scheduled`, Quartz job | Tần suất, khóa chống chạy trùng, checkpoint và retry? |
| Message consumer | `@KafkaListener`, `@RabbitListener` | Message schema, ack/retry, idempotency và dead-letter? |
| Batch | Spring Batch, importer tùy chỉnh | Đọc theo chunk nào, transaction và phục hồi ra sao? |
| Internal call | Service hoặc module gọi trực tiếp | Consumer nào gọi, có phụ thuộc giao thức hoặc context ngầm không? |

Mỗi điểm vào có thể chuyển dữ liệu thành command/query rồi gọi cùng ca sử dụng, hoặc có thể chứa logic riêng. Hãy ghi lại điều đó thay vì giả định rằng mọi controller hoặc job đều gọi đúng một application service.

Một bảng kiểm kê tối thiểu có thể gồm tên điểm vào, chức năng, consumer, xác thực/ủy quyền, thành phần tiếp theo, dữ liệu bị tác động và mức độ quan trọng. Bảng này giúp phát hiện những luồng không xuất hiện trong sơ đồ web thông thường.

## 5. Lần theo một luồng xử lý từ đầu đến cuối

Với từng điểm vào quan trọng, theo dõi tuần tự các bước:

1. **Nhận dữ liệu:** path, query, body, header, message payload, CLI argument hoặc dữ liệu batch.
2. **Chuyển đổi:** DTO, command, entity, model hoặc map được tạo ở đâu?
3. **Kiểm tra:** validation cú pháp, xác thực danh tính, phân quyền và quy tắc nghiệp vụ được thực hiện ở đâu?
4. **Điều phối:** thành phần nào quyết định thứ tự các thao tác và gọi các dependency?
5. **Đọc/ghi:** repository, DAO, JDBC, ORM hoặc truy vấn thủ công nào được sử dụng?
6. **Tác dụng phụ:** event, email, cache, file, API ngoài hoặc audit được thực hiện khi nào?
7. **Kết thúc:** transaction commit/rollback, response, ack message, exit code hoặc trạng thái batch được tạo ở đâu?
8. **Lỗi:** exception nào có thể phát sinh, được bắt ở đâu và retry theo quy tắc nào?

Sơ đồ trình tự ví dụ:

~~~mermaid
sequenceDiagram
    participant Client
    participant Controller
    participant OrderService
    participant OrderRepository
    participant Database
    participant MailGateway
    Client->>Controller: POST /orders
    Controller->>OrderService: create(command)
    OrderService->>OrderRepository: save(order)
    OrderRepository->>Database: INSERT order
    Database-->>OrderRepository: generated id
    OrderRepository-->>OrderService: saved order
    OrderService->>MailGateway: sendConfirmation(order)
    OrderService-->>Controller: result
    Controller-->>Client: HTTP response
~~~

Sơ đồ chỉ mô tả một luồng thành công đơn giản. Khi khảo sát hệ thống thật, hãy bổ sung các nhánh lỗi, transaction và thứ tự phát event. Đặc biệt, cần xác định email được gửi trước hay sau khi transaction commit. Nếu email gửi thành công nhưng database rollback, hệ thống có thể gửi thông báo về một đơn chưa tồn tại. Nếu email được gửi sau commit nhưng tiến trình dừng trước khi gửi, thông báo có thể bị mất. Đây là thông tin kiến trúc quan trọng, không thể suy ra chỉ từ tên method.

### Theo dõi dữ liệu qua từng bước

Với mỗi biến hoặc đối tượng quan trọng, ghi nhận:

- Nguồn dữ liệu: client, database, token đã xác thực, config hay hệ thống ngoài.
- Kiểu dữ liệu: HTTP DTO, command, domain object, JPA entity, map hay primitive.
- Nơi chuyển đổi và quy tắc chuyển đổi.
- Ai được phép sửa dữ liệu và thời điểm trạng thái thay đổi.
- Giá trị có bị dùng lại ở nhiều tầng hoặc lưu vào context/thread-local không.

Nếu một JPA entity được truyền từ repository lên controller rồi serialize trực tiếp, đây là dấu hiệu mô hình lưu trữ đã đi qua ranh giới. Nếu một `HttpServletRequest` được truyền sâu xuống service, tầng ứng dụng có thể đang phụ thuộc vào giao thức trình bày. Nếu một `Map<String, Object>` đi qua nhiều tầng, cần tìm hiểu hợp đồng dữ liệu có quá lỏng lẻo hay không.

## 6. Phân loại trách nhiệm thực tế

Tên package hoặc annotation chỉ là gợi ý. Hãy đọc hành vi và phân loại từng trách nhiệm theo câu hỏi mà nó giải quyết.

| Trách nhiệm | Tầng thường sở hữu | Dấu hiệu trong mã nguồn |
|---|---|---|
| Giao thức và trình bày | Presentation | HTTP status, request/response DTO, JSON, view, CLI output. |
| Điều phối ca sử dụng | Application | Trình tự thao tác, transaction boundary, gọi port, phối hợp nhiều bước. |
| Quy tắc nghiệp vụ | Domain/business | Invariant, tính giá, chuyển trạng thái, điều kiện được phép. |
| Truy cập dữ liệu | Data access | SQL, ORM mapping, JDBC, repository adapter, cache lưu trữ. |
| Tích hợp bên ngoài | Adapter/infrastructure theo thiết kế | HTTP client, message broker, file system, email gateway. |

Một lớp có thể chứa nhiều trách nhiệm. Khi đó, hãy ghi nhận từng method hoặc đoạn logic thay vì gắn một nhãn duy nhất cho cả file. Ví dụ `OrderService` có thể vừa điều phối ca sử dụng, vừa tính giá, vừa tạo SQL, vừa gửi email. Kết luận “OrderService thuộc application layer” không làm các trách nhiệm còn lại tự động trở thành đúng tầng.

Không phải hệ thống nào cũng có một domain layer độc lập hoặc mô hình DDD đầy đủ. Trong ứng dụng nhỏ, quy tắc nghiệp vụ có thể nằm trong service hoặc model đơn giản. Điều cần tìm là nơi quy tắc được thực thi và có bị sao chép hoặc phụ thuộc vào framework hay không, chứ không ép hệ thống phải có một số lớp cố định.

## 7. Nhận diện ranh giới đang trộn lẫn

### Controller làm nghiệp vụ và truy cập dữ liệu

~~~java
import java.math.BigDecimal;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

record CreateOrderRequest(BigDecimal price, int quantity) {}

@RestController
class OrderController {
    private final JdbcTemplate jdbc;

    OrderController(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @PostMapping("/orders")
    ResponseEntity<?> create(@RequestBody CreateOrderRequest request) {
        if (request.quantity() <= 0) {
            return ResponseEntity.badRequest().build();
        }

        var total = request.price().multiply(
                BigDecimal.valueOf(request.quantity()));
        jdbc.update("insert into orders(total) values (?)", total);
        return ResponseEntity.ok().build();
    }
}
~~~

Trong ví dụ, controller đang làm ít nhất ba việc: xử lý HTTP, kiểm tra điều kiện đầu vào/nghiệp vụ và ghi database. Việc kiểm tra số lượng dương có thể là validation đầu vào, nhưng nếu quy tắc còn phụ thuộc sản phẩm, khách hàng hoặc trạng thái thì cần được kiểm tra trong ca sử dụng/mô hình nghiệp vụ. Controller cũng biết schema và công nghệ JDBC.

Khi khảo sát, đừng chỉ ghi “controller quá lớn”. Hãy tách trách nhiệm: ánh xạ request, kiểm tra hình thức, tính toán nghiệp vụ, ghi dữ liệu và tạo response. Mỗi trách nhiệm sẽ dẫn đến một ranh giới cần đánh giá khác nhau.

### Application service biết chi tiết giao thức

Dấu hiệu gồm `HttpServletRequest`, `ResponseEntity`, `HttpStatus`, `MultipartFile` hoặc annotation MVC xuất hiện trong lớp điều phối. Điều này khiến cùng ca sử dụng khó được gọi từ scheduler, CLI hoặc message consumer. Cần xác định chính xác dữ liệu giao thức nào đang được dùng và liệu có thể chuyển thành command/context độc lập giao thức hay không.

### Domain model phụ thuộc hạ tầng

Entity nghiệp vụ có thể mang annotation ORM vì một số dự án chọn cách đó. Đây không tự động là lỗi. Tuy nhiên, nếu quy tắc nghiệp vụ phụ thuộc `EntityManager`, Spring Security, HTTP session hoặc gọi API ngoài trực tiếp, mô hình nghiệp vụ có thể đang gắn chặt với hạ tầng. Hãy ghi rõ dependency nào cần thiết, dependency nào chỉ xuất hiện do tiện lợi triển khai.

### Repository chứa quy tắc điều phối

Repository nên tập trung vào truy xuất và lưu trữ. Nếu repository quyết định đơn hàng nào cần phê duyệt, gửi email hoặc điều phối nhiều use case, nó có thể đang gánh trách nhiệm ngoài data access. Một số truy vấn chuyên biệt vẫn có thể chứa điều kiện lọc dữ liệu; cần phân biệt điều kiện truy vấn với quyết định nghiệp vụ.

### Nhiều nơi cùng thực hiện một quy tắc

Ví dụ, controller kiểm tra tồn kho, `OrderService` kiểm tra lại theo cách khác, và batch import bỏ qua hoàn toàn. Đây là dấu hiệu quy tắc không có một nơi sở hữu rõ ràng. Cần tìm tất cả nơi đọc/ghi hoặc tính toán liên quan, so sánh hành vi và xác định nơi nên bảo vệ invariant.

### Dependency vòng và phụ thuộc ngược

Một package application import controller, domain import repository JPA, hoặc hai module gọi trực tiếp lẫn nhau có thể tạo dependency ngược hoặc vòng. Chu trình làm khó khởi tạo, kiểm thử và thay đổi độc lập. Hãy phân biệt dependency tĩnh ở compile time với lời gọi callback lúc chạy; đôi khi dependency inversion tạo ra luồng gọi runtime ngược chiều nhưng dependency compile-time vẫn hướng về abstraction đúng.

## 8. Lập đồ thị phụ thuộc có ích

Không cần vẽ mọi lớp. Hãy bắt đầu ở mức module/package và mở rộng các nút liên quan đến ca sử dụng đã chọn. Mỗi cạnh nên thể hiện loại quan hệ:

- **Compile-time:** import, tham chiếu kiểu, kế thừa hoặc module dependency.
- **Runtime call:** gọi method, gửi message, callback hoặc truy vấn.
- **Data dependency:** đọc/ghi cùng bảng, file, cache key hoặc schema.
- **Configuration dependency:** bean được tạo bởi config, profile, reflection hoặc tên lớp.
- **Deployment dependency:** cần database, broker, file share hoặc dịch vụ ngoài để chạy.

Ví dụ đồ thị hiện trạng có thể trông như sau:

~~~mermaid
flowchart TD
    Web[web / controllers] --> App[services]
    Web --> DB[JdbcTemplate / JPA]
    App --> DB
    App --> Domain[domain models]
    Batch[batch jobs] --> App
    Batch --> DB
    App --> Mail[mail client]
    DB --> Store[(orders database)]
~~~

Sơ đồ này cho thấy controller và batch cùng truy cập database, còn service vừa dùng domain model vừa dùng persistence. Đây là bản đồ hiện trạng, chưa phải sơ đồ đích. Không nên sửa sơ đồ để làm cho kiến trúc trông đẹp hơn trước khi xác minh mã nguồn.

### Ghi chú mức độ chắc chắn

Mỗi cạnh có thể được đánh dấu:

- **Đã xác minh:** thấy trong mã hoặc trace của kịch bản cụ thể.
- **Có khả năng:** suy ra từ cấu hình, annotation hoặc call site nhưng chưa quan sát lúc chạy.
- **Chưa rõ:** reflection, cấu hình ngoài hoặc đường gọi hiếm chưa được kiểm tra.

Ghi mức độ chắc chắn giúp tránh coi một sơ đồ chưa hoàn chỉnh là sự thật tuyệt đối. Nếu một dependency động quan trọng chưa rõ, hãy ghi thành câu hỏi điều tra thay vì tự suy đoán.

## 9. Tìm kiếm và công cụ khảo sát trong Java

### Đọc mã nguồn có định hướng

Tìm điểm vào trước, sau đó lần theo method được gọi và kiểu dependency trong constructor. Tìm các dấu hiệu truy cập hạ tầng như `JdbcTemplate`, `EntityManager`, `DataSource`, `RestTemplate`, `WebClient`, message template hoặc file API. Tìm các dấu hiệu giao thức như `HttpServletRequest`, `ResponseEntity`, `@RequestMapping`, `MultipartFile` và annotation bảo mật.

Tìm kiếm văn bản giúp tìm nhanh call site, nhưng không thay thế phân tích kiểu và cấu hình. Một bean có thể được tạo bằng `@Bean`, profile hoặc auto-configuration; một lời gọi có thể được thực hiện qua proxy hoặc reflection. Hãy mở rộng điều tra khi bằng chứng chỉ ra các cơ chế đó.

### Phân tích dependency tĩnh

Các công cụ như IDE dependency analysis, `jdeps` hoặc ArchUnit có thể hỗ trợ:

- Xem module/package nào phụ thuộc module/package nào.
- Phát hiện dependency vòng ở mức package.
- Kiểm tra lớp trong package presentation có import persistence không.
- Xác minh domain package không phụ thuộc Spring Web hoặc adapter cụ thể nếu đó là quy tắc của dự án.

`jdeps` phân tích dependency ở mức bytecode/package/module, không hiểu đầy đủ ý nghĩa nghiệp vụ hoặc mọi quan hệ runtime. ArchUnit kiểm tra quy tắc trên bytecode và cần được cấu hình đúng package. Công cụ cung cấp bằng chứng cấu trúc; con người vẫn phải diễn giải trách nhiệm.

### Quan sát lúc chạy

Log có correlation ID, distributed tracing, JFR, APM hoặc debugger có thể giúp lần theo luồng thực tế. Hãy chọn một số kịch bản đại diện và quan sát cả thời gian, lỗi, truy vấn, event lẫn transaction. Tránh bật logging quá chi tiết trên production nếu nó tạo overhead hoặc ghi dữ liệu nhạy cảm.

### Kiểm tra database và dữ liệu dùng chung

Tìm nơi thực hiện truy vấn, stored procedure, view, trigger và job ngoài ứng dụng. Kiểm tra quyền database, schema ownership, migration và consumer khác. Một ứng dụng Java có thể không phải nơi duy nhất cập nhật dữ liệu; công cụ ETL, báo cáo, script vận hành hoặc hệ thống cũ có thể cùng ghi vào database.

## 10. Phân tích dependency vòng và trách nhiệm bị phân tán

Dependency vòng thường biểu hiện theo hai dạng:

1. **Vòng compile-time:** module A tham chiếu B, B tham chiếu C và C tham chiếu lại A.
2. **Vòng runtime/điều phối:** A gọi B, B gọi callback C và C gọi ngược A; có thể không tạo vòng import nhưng vẫn làm luồng xử lý khó hiểu.

Ví dụ, `OrderService` gọi `CustomerService` để kiểm tra hạn mức, còn `CustomerService` gọi `OrderService` để tính tổng đơn chưa thanh toán. Cả hai đang cần một phần thông tin của nhau. Cần xác định quy tắc nào thuộc khách hàng, quy tắc nào thuộc đơn hàng và ai điều phối việc phối hợp. Có thể cần một query/port nhỏ hơn hoặc một use case điều phối ở tầng ứng dụng.

Đừng phá vòng bằng cách chuyển tất cả logic vào một `CommonService` hoặc tạo interface rỗng chỉ để compiler chấp nhận. Trước hết hãy xác định trách nhiệm và dữ liệu thực sự cần trao đổi. Một abstraction tốt diễn đạt hợp đồng có ý nghĩa, không chỉ che giấu một chu trình.

Trách nhiệm phân tán cũng xuất hiện khi cùng một quy tắc được lặp ở nhiều controller, service và batch. Hãy tìm theo tên trạng thái, điều kiện, trường dữ liệu và truy vấn, không chỉ tìm theo tên method. Quy tắc có thể được viết dưới nhiều cách khác nhau.

## 11. Ghi nhận kết quả khảo sát

Một khảo sát hữu ích tạo ra một số hiện vật nhỏ, có thể dùng trong review và lập kế hoạch:

| Hiện vật | Nội dung | Mục đích |
|---|---|---|
| Danh sách điểm vào | Endpoint, job, CLI, consumer, batch | Biết những nơi có thể khởi chạy hành vi. |
| Dependency graph | Module/lớp và loại quan hệ | Thấy hướng phụ thuộc, vòng và truy cập xuyên tầng. |
| Sequence/flow diagram | Các bước, dữ liệu và tác dụng phụ | Hiểu thứ tự thực thi, transaction và lỗi. |
| Responsibility map | Thành phần và trách nhiệm thực tế | Xác định nơi logic đang bị trộn lẫn hoặc trùng lặp. |
| Data ownership map | Bảng/schema, consumer, reader/writer | Biết ai sở hữu dữ liệu và mọi đường ghi. |
| Risk/findings list | Bằng chứng, tác động, độ chắc chắn, ưu tiên | Chọn phạm vi refactor có giá trị và rủi ro phù hợp. |

Mỗi finding nên có mô tả cụ thể, ví dụ:

~~~text
Finding: OrderController ghi trực tiếp bảng orders

Bằng chứng:
- OrderController inject JdbcTemplate và thực hiện INSERT.
- OrderService cũng có thao tác lưu đơn qua OrderRepository.
- OrderImportJob gọi OrderRepository nhưng bỏ qua kiểm tra trạng thái ở controller.

Tác động:
- Hai đường tạo đơn có thể áp dụng quy tắc khác nhau.
- Controller phụ thuộc schema và công nghệ JDBC.
- Khó bảo đảm audit và transaction nhất quán.

Độ chắc chắn: Đã xác minh trong mã nguồn; hành vi production cần đối chiếu trace.
Phạm vi tiếp theo: So sánh quy tắc tạo đơn ở HTTP và batch, xác định test bảo vệ trước khi thay đổi.
~~~

Không ghi finding chung chung như “code xấu”, “service quá lớn” hoặc “cần clean architecture”. Hãy nêu bằng chứng, tác động và câu hỏi cần xác minh. Một lớp dài chưa chắc là vấn đề nếu nó có một trách nhiệm rõ; một lớp ngắn vẫn có thể vi phạm ranh giới nếu phụ thuộc sai tầng.

## 12. Xác định ưu tiên dựa trên tác động và độ chắc chắn

Không phải mọi vi phạm đều cần sửa ngay. Có thể xếp ưu tiên theo hai trục:

- **Tác động:** ảnh hưởng đến tính đúng đắn dữ liệu, bảo mật, khả năng thay đổi, độ tin cậy, hiệu năng hoặc tốc độ phát triển.
- **Độ chắc chắn:** đã quan sát được trong mã/trace/test hay mới là giả thuyết.

| Mức ưu tiên | Dấu hiệu | Hành động phù hợp |
|---|---|---|
| Cao | Có thể gây dữ liệu sai, bỏ qua quyền, mất giao dịch hoặc lỗi production tái hiện được | Bổ sung kiểm thử bảo vệ, xác minh đường ghi và xử lý rủi ro trước. |
| Trung bình | Phụ thuộc xuyên tầng làm một thay đổi thường xuyên lan rộng hoặc gây lỗi tích hợp | Chọn một vertical slice để cải thiện ranh giới và theo dõi. |
| Thấp | Tên package, cấu trúc lớp hoặc trùng lặp nhỏ chưa gây ảnh hưởng rõ | Ghi nhận, cân nhắc khi có thay đổi liên quan; tránh refactor diện rộng không có mục tiêu. |
| Cần điều tra | Chỉ có dấu hiệu từ cấu hình động hoặc một trace chưa đại diện | Thu thập thêm bằng chứng trước khi quyết định. |

Một dependency sai hướng trong module lõi có thể đáng ưu tiên hơn một controller dài nhưng ổn định. Ngược lại, một đường ghi trực tiếp vào dữ liệu tài chính có thể cần xử lý trước dù chỉ xuất hiện ở một lớp nhỏ. Hãy ưu tiên theo rủi ro thật, không theo độ khó nhìn thấy của code.

## 13. Bảo vệ hành vi trước khi bắt đầu thay đổi

Khảo sát kiến trúc nên đi cùng việc xác định hành vi cần giữ. Trước khi di chuyển trách nhiệm, hãy tìm hoặc bổ sung characterization test cho luồng hiện tại:

- Input hợp lệ tạo ra kết quả và tác dụng phụ nào?
- Input sai hoặc actor không có quyền bị xử lý ra sao?
- Các trạng thái nghiệp vụ được chuyển theo điều kiện nào?
- Transaction commit/rollback ở đâu?
- Event, email hoặc lời gọi ngoài được thực hiện trước hay sau commit?
- Hành vi khi timeout, retry hoặc xử lý message trùng là gì?

Characterization test ghi nhận hành vi đang tồn tại; nó không mặc nhiên khẳng định mọi hành vi hiện tại đều đúng về nghiệp vụ. Khi phát hiện hành vi sai, cần phân biệt bug đã biết với hành vi cần giữ trong giai đoạn refactor để tránh thay đổi ngoài dự kiến.

Không nên viết test chỉ để khóa chặt cấu trúc private method hoặc số lượng lớp. Hãy kiểm tra qua hợp đồng và kết quả quan sát được, đồng thời bổ sung test kiến trúc cho những hướng phụ thuộc quan trọng.

## 14. Ví dụ khảo sát một luồng tạo đơn hàng

Giả sử hệ thống hiện tại có các thành phần sau:

| Thành phần | Hành vi tìm thấy | Nhận định ban đầu |
|---|---|---|
| `OrderController` | Nhận JSON, kiểm tra quantity, tính tổng và gọi JDBC | Trộn presentation, nghiệp vụ và data access. |
| `OrderService` | Kiểm tra trạng thái, áp dụng giảm giá, gọi repository | Có điều phối ứng dụng và quy tắc nghiệp vụ. |
| `OrderRepository` | Lưu và đọc JPA entity | Data access, nhưng cần xem có consumer ngoài module không. |
| `OrderImportJob` | Đọc CSV, gọi repository trực tiếp, tự kiểm tra một phần | Adapter batch có thể bỏ qua một số quy tắc của service. |
| `NotificationClient` | Gửi email sau khi lưu đơn | Tác dụng phụ ngoài; cần xác định thứ tự với transaction. |

Đồ thị hiện trạng:

~~~mermaid
flowchart TD
    HTTP[OrderController] --> S[OrderService]
    HTTP --> JDBC[JdbcTemplate]
    JOB[OrderImportJob] --> REPO[OrderRepository]
    S --> REPO
    S --> DOMAIN[Order / Pricing rules]
    S --> MAIL[NotificationClient]
    REPO --> DB[(orders database)]
    JDBC --> DB
~~~

Từ sơ đồ và luồng xử lý, có thể đặt ra các giả thuyết cần kiểm chứng:

1. HTTP và batch có thể tạo đơn theo quy tắc khác nhau vì đi qua hai đường ghi.
2. Controller phụ thuộc trực tiếp vào schema qua JDBC.
3. Quy tắc giảm giá có thể nằm trong `OrderService`, nhưng cần tìm xem controller hoặc job có tính lại theo cách riêng không.
4. Email có thể được gửi trong transaction hoặc trước khi commit; cần xác minh thứ tự thực tế.
5. `OrderRepository` có thể đang công bố JPA entity ra ngoài module.

Các bước điều tra tiếp theo là đọc call site của `OrderService` và repository, lần theo batch job, kiểm tra query và transaction, quan sát trace/log, rồi xác định test hiện có. Chỉ sau khi xác minh mới chọn phạm vi refactor, chẳng hạn đưa cả HTTP và batch qua cùng ca sử dụng tạo đơn và giữ truy vấn sau hợp đồng dữ liệu.

## 15. Những sai lầm khi khảo sát hệ thống cũ

- **Chỉ đọc cấu trúc thư mục:** tên `service`, `domain`, `repository` không chứng minh trách nhiệm thực tế.
- **Chỉ khảo sát HTTP:** bỏ lỡ scheduler, batch, CLI, consumer và script vận hành.
- **Chỉ vẽ dependency tĩnh:** bỏ lỡ proxy, reflection, callback, event và tác dụng phụ lúc chạy.
- **Chỉ xem trace thành công:** bỏ lỡ nhánh lỗi, retry, rollback và xử lý message trùng.
- **Giả định một bảng chỉ có một writer:** bỏ lỡ ETL, báo cáo, ứng dụng cũ hoặc công cụ vận hành.
- **Coi mọi dependency trực tiếp là sai:** tạo interface và lớp trung gian không cần thiết.
- **Vẽ sơ đồ đích thay cho hiện trạng:** che giấu vấn đề cần khảo sát và làm người đọc hiểu sai hệ thống đang chạy.
- **Refactor ngay trong lúc chưa hiểu luồng:** thay đổi quá nhiều thứ cùng lúc, khó biết nguyên nhân nếu hành vi bị hỏng.
- **Gắn nhãn mọi vấn đề là technical debt:** không nêu bằng chứng, tác động hoặc mức ưu tiên cụ thể.

## 16. Tự rà soát trước khi lập kế hoạch refactor

1. Đã xác định các điểm vào chính và consumer dùng chung thành phần chưa?
2. Có dependency graph tĩnh và bằng chứng runtime cho các luồng quan trọng chưa?
3. Đã lần theo dữ liệu từ đầu vào đến nơi đọc/ghi và các tác dụng phụ chưa?
4. Đã phân biệt trách nhiệm trình bày, điều phối, nghiệp vụ và truy cập dữ liệu chưa?
5. Có dependency vòng, truy cập xuyên tầng hoặc nhiều đường ghi vào cùng dữ liệu không?
6. Những giả thuyết nào đã được xác minh, những điều nào vẫn chưa rõ?
7. Đã xác định hành vi cần bảo vệ bằng characterization/integration test chưa?
8. Finding có bằng chứng, tác động, độ chắc chắn và phạm vi điều tra tiếp theo không?
9. Có thể chọn một vertical slice nhỏ để refactor và xác nhận kết quả không?

## Kết luận

Khảo sát hệ thống hiện có cần kết hợp ba góc nhìn: đồ thị phụ thuộc cho biết các thành phần liên kết ra sao, luồng xử lý cho biết yêu cầu và tác dụng phụ thực sự đi qua đâu, còn phân tích trách nhiệm cho biết ranh giới nào đang bị trộn lẫn. Hãy bắt đầu từ một vertical slice có giá trị, liệt kê mọi điểm vào và đường đọc/ghi, đối chiếu mã nguồn với trace và test, rồi ghi nhận finding bằng bằng chứng cùng mức độ chắc chắn. Bản đồ hiện trạng đủ tin cậy giúp chọn phạm vi refactor nhỏ, bảo vệ hành vi quan trọng và tránh biến việc cải tiến kiến trúc thành một cuộc viết lại thiếu kiểm soát.
