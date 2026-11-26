# Rà soát trách nhiệm, hợp đồng và quyền sở hữu của từng tầng

*Chương: Sai lầm và đánh giá thiết kế*

Bài học này thuộc module `SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED`, có mục tiêu **Học tổ chức phần mềm theo kiến trúc phân tầng**. Khi rà soát một thiết kế phân tầng, câu hỏi quan trọng không phải là dự án có đủ package mang tên presentation, application, domain và data access hay không. Cần xác định mỗi thành phần đang chịu trách nhiệm gì, hợp đồng giữa nó với thành phần khác có rõ ràng không, và tầng nào thực sự sở hữu quy tắc hoặc dữ liệu đang được xử lý.

Một thiết kế có thể có cấu trúc thư mục đẹp nhưng vẫn khó thay đổi nếu controller tự quyết định quy tắc nghiệp vụ, repository chứa luồng điều phối, hoặc nhiều tầng cùng sửa trạng thái theo cách riêng. Ngược lại, một ứng dụng nhỏ có ít package vẫn có thể phân tầng tốt nếu mỗi trách nhiệm có nơi chịu trách nhiệm rõ, phụ thuộc đi theo hướng có chủ đích và các ranh giới được kiểm thử.

Bài học này trình bày cách đánh giá trách nhiệm, hợp đồng và quyền sở hữu bằng một luồng đặt hàng trong Java/Spring. Các nhóm tầng dưới đây là mô hình tham khảo; dự án có thể gộp hoặc tách chúng tùy quy mô và độ phức tạp. Không có một số lượng tầng duy nhất bắt buộc cho mọi hệ thống.

## 1. Ba câu hỏi cốt lõi khi review

Với mỗi lớp, package hoặc module, hãy đặt ba câu hỏi:

1. **Trách nhiệm:** Thành phần này tồn tại để làm công việc gì? Nó có đang làm thêm việc thuộc một lý do thay đổi khác không?
2. **Hợp đồng:** Thành phần nhận gì, trả gì, có thể báo lỗi nào và những điều kiện nào caller được phép kỳ vọng?
3. **Quyền sở hữu:** Ai có thẩm quyền quyết định quy tắc, thay đổi trạng thái hoặc duy trì dữ liệu này? Có nhiều nơi cùng sửa mà không có một nơi kiểm soát không?

Ba câu hỏi liên quan chặt chẽ. Nếu trách nhiệm không rõ, hợp đồng thường phơi bày quá nhiều chi tiết. Nếu hợp đồng không rõ, caller dễ dựa vào hành vi ngầm. Nếu quyền sở hữu không rõ, một quy tắc có thể bị sao chép hoặc bị thay đổi từ nhiều đường đi khác nhau.

Ví dụ, khi hủy đơn hàng, controller có thể nhận request và gọi use case; application service xác định các bước của ca sử dụng; mô hình đơn hàng quyết định trạng thái hiện tại có cho phép hủy hay không; repository chịu trách nhiệm lưu trạng thái. Nếu controller, service và repository đều tự kiểm tra rồi tự đặt trạng thái `CANCELLED`, quyền sở hữu quy tắc đã bị phân tán.

## 2. Rà soát trách nhiệm của từng tầng

Bảng sau là điểm bắt đầu để đánh giá một thiết kế phổ biến:

| Tầng | Trách nhiệm chính | Không nên trở thành nơi |
|---|---|---|
| Trình bày (presentation) | Giao tiếp với HTTP/UI, kiểm tra cấu trúc đầu vào, chuyển đổi request/response | Nơi chứa toàn bộ quy tắc nghiệp vụ hoặc SQL |
| Ứng dụng (application) | Điều phối ca sử dụng, quản lý ranh giới công việc, phối hợp các cổng và dịch vụ | Một bản sao của mô hình nghiệp vụ hoặc nơi biết chi tiết giao thức/lưu trữ |
| Nghiệp vụ/miền (business/domain) | Biểu diễn khái niệm, trạng thái, hành vi và bất biến nghiệp vụ | Nơi phụ thuộc vào HTTP, schema database hoặc framework web |
| Truy cập dữ liệu (data access) | Thực hiện truy vấn, mapping và thao tác lưu trữ | Nơi tự quyết định toàn bộ luồng nghiệp vụ hoặc trả HTTP response |

### Tầng trình bày

Tầng trình bày biết về giao thức mà nó phục vụ. Với REST API, nó có thể biết HTTP method, status code, header, JSON và Bean Validation. Nó chuyển dữ liệu giao tiếp thành command hoặc query mà tầng ứng dụng hiểu.

Một controller nên mỏng theo nghĩa trách nhiệm rõ ràng, không phải vì số dòng phải ít. Nếu controller thực hiện phép tính giá, quyết định chuyển trạng thái, tự mở transaction, truy cập nhiều repository và gửi email, nó đang sở hữu quá nhiều lý do thay đổi. Khi API đổi định dạng, quy tắc nghiệp vụ không nên phải thay đổi theo.

### Tầng ứng dụng

Tầng ứng dụng thể hiện một ca sử dụng: tạo đơn, xác nhận đơn, hủy đơn hoặc tra cứu lịch sử. Nó có thể tải đối tượng, kiểm tra quyền ở phạm vi ca sử dụng, gọi hành vi nghiệp vụ, lưu kết quả và phối hợp các bước khác.

Application service không nhất thiết chứa quy tắc chi tiết của miền. Ví dụ, nó có thể gọi `order.cancel()` thay vì tự kiểm tra từng trạng thái và gán `order.setStatus(CANCELLED)`. Nó điều phối *khi nào* các khả năng được gọi; mô hình nghiệp vụ quyết định *hành động đó có hợp lệ hay không* theo quy tắc mà nó sở hữu.

### Tầng nghiệp vụ

Tầng nghiệp vụ biểu diễn ý nghĩa của hệ thống: đơn hàng là gì, trạng thái nào hợp lệ, điều kiện xác nhận hoặc hủy là gì. Một quy tắc có thể nằm trong entity/value object nếu nó gắn với khái niệm đó, hoặc trong domain service nếu quy tắc phối hợp nhiều khái niệm mà không thuộc tự nhiên về một đối tượng đơn lẻ.

Không phải mọi ứng dụng đều cần mô hình miền phức tạp hoặc áp dụng đầy đủ DDD. Với CRUD đơn giản, mô hình dữ liệu mỏng có thể phù hợp. Nhưng khi có bất biến và chuyển trạng thái quan trọng, cần xác định rõ nơi bảo vệ chúng để các đường vào không tự diễn giải khác nhau.

### Tầng truy cập dữ liệu

Tầng truy cập dữ liệu biết về JPA, JDBC, SQL, schema, index và cách chuyển đổi dữ liệu lưu trữ. Nó thực hiện hợp đồng mà tầng trong yêu cầu. Repository có thể trả về mô hình nghiệp vụ hoặc projection phù hợp với use case, tùy thiết kế.

Không nên để controller gọi `EntityManager` hoặc tự tạo câu SQL. Cũng không nên để repository âm thầm quyết định một quy tắc như “đơn hàng này được phép hủy” bằng cách chỉ trả về các bản ghi phù hợp rồi coi đó là toàn bộ quyết định nghiệp vụ. Truy vấn có thể hỗ trợ quyết định; quyền sở hữu quy tắc cần rõ ràng.

## 3. Phân biệt tầng logic với tier triển khai

Khi review, hãy kiểm tra nhóm có đang nhầm kiến trúc logic với cách triển khai hay không. Controller, application service, domain model và repository adapter có thể nằm trong cùng một ứng dụng Spring Boot, cùng chạy trong một JVM và cùng được triển khai trên một máy chủ. Chúng vẫn là những tầng logic khác nhau.

Ngược lại, một tier triển khai là một tiến trình hoặc môi trường thực thi được phân tách, ví dụ web application gọi một database server qua mạng. Tách tầng logic không tự động yêu cầu tạo microservice, container riêng hoặc dịch vụ mạng cho mỗi tầng.

Việc phân tách deployment có thể hữu ích khi cần mở rộng độc lập, cô lập lỗi, quyền vận hành hoặc chu kỳ phát hành riêng. Nhưng nó cũng thêm độ trễ mạng, lỗi phân tán, quản lý phiên bản và chi phí vận hành. Review nên hỏi lý do triển khai trước khi kết luận rằng mỗi tầng cần một tiến trình riêng.

## 4. Đánh giá hợp đồng ở mỗi ranh giới

Hợp đồng không chỉ là chữ ký phương thức. Nó gồm dữ liệu vào/ra, ngữ nghĩa, điều kiện, lỗi và tác dụng phụ mà caller có thể dựa vào.

| Nội dung hợp đồng | Câu hỏi review |
|---|---|
| Đầu vào | Caller cần cung cấp những gì? Trường nào bắt buộc, trường nào có thể vắng mặt? |
| Đầu ra | Thành phần trả entity, DTO, kết quả nghiệp vụ hay trạng thái xử lý? |
| Ngữ nghĩa | Các trường có đơn vị, múi giờ, độ chính xác và ý nghĩa rõ ràng không? |
| Lỗi | Những lỗi dự kiến nào có thể xảy ra? Caller phân biệt lỗi nghiệp vụ với lỗi kỹ thuật ra sao? |
| Tác dụng phụ | Thành phần có lưu dữ liệu, phát event hoặc gọi dịch vụ bên ngoài không? |
| Transaction | Những thay đổi nào được commit cùng nhau? |
| Tương thích | Thay đổi chữ ký hoặc schema có ảnh hưởng caller hiện tại không? |

Ví dụ, `OrderRepository.findById(OrderId)` có thể trả `Optional<Order>`, nghĩa là đơn có thể không tồn tại. Hợp đồng này không nên buộc caller biết `EntityManager` hoặc tên bảng. Tương tự, `POST /api/orders` có thể nhận `CreateOrderRequest` và trả `OrderResponse`; API không cần trả trực tiếp JPA entity với mọi quan hệ nội bộ.

Một hợp đồng tốt nói rõ những gì caller cần biết và che giấu chi tiết implementation không thuộc về caller. Tuy nhiên, abstraction quá mơ hồ cũng có hại. Một phương thức `process(Object data)` không diễn đạt rõ nghiệp vụ, kiểu dữ liệu hay lỗi. Hãy giữ hợp đồng cụ thể đủ để người sử dụng hiểu cách gọi và dự đoán kết quả.

## 5. Rà soát quyền sở hữu dữ liệu và trạng thái

Quyền sở hữu trong thiết kế phân tầng không có nghĩa một lớp phải là nơi vật lý duy nhất chứa dữ liệu. Nó có nghĩa một thành phần hoặc ranh giới được giao trách nhiệm bảo vệ ý nghĩa và quy tắc thay đổi của dữ liệu.

Ví dụ với đơn hàng:

- Mô hình `Order` sở hữu các chuyển trạng thái hợp lệ như xác nhận, giao và hủy.
- Application service sở hữu trình tự của use case, chẳng hạn tải đơn, kiểm tra quyền, yêu cầu hủy và lưu kết quả.
- Repository sở hữu cách đọc/ghi đơn hàng vào nơi lưu trữ.
- Controller sở hữu cách biểu diễn kết quả của use case thành HTTP response.

Database vẫn có thể đặt constraint để bảo vệ dữ liệu trước cập nhật đồng thời hoặc đường ghi khác. Điều đó không làm database trở thành nơi duy nhất diễn đạt mọi quy tắc. Ràng buộc duy nhất, khóa ngoại và not-null là lớp bảo vệ lưu trữ; ý nghĩa nghiệp vụ và phản hồi phù hợp vẫn cần được mô hình hóa ở ứng dụng.

Khi nhiều module hoặc dịch vụ cùng cập nhật một loại dữ liệu, cần xác định nguồn có thẩm quyền (source of truth), quy tắc đồng bộ và hợp đồng tích hợp. Không nên để hai dịch vụ cùng sửa trực tiếp một bảng dùng chung mà không có thỏa thuận về quyền sở hữu, vì mỗi bên có thể phá vỡ bất biến mà bên kia kỳ vọng.

## 6. Ví dụ review một luồng hủy đơn hàng

Giả sử hệ thống chỉ cho phép hủy đơn khi đơn còn ở trạng thái `DRAFT` hoặc `CONFIRMED` và chưa được giao. Một thiết kế thiếu ranh giới có thể trông như sau:

~~~java
@RestController
public class OrderController {
    private final OrderRepository orders;
    private final EmailClient emailClient;

    @PostMapping("/api/orders/{id}/cancel")
    public ResponseEntity<?> cancel(@PathVariable UUID id) {
        Order order = orders.findById(id).orElseThrow();

        if (order.getStatus() == OrderStatus.SHIPPED) {
            return ResponseEntity.badRequest().build();
        }

        order.setStatus(OrderStatus.CANCELLED);
        orders.save(order);
        emailClient.sendCancellation(order.getCustomerEmail());

        return ResponseEntity.ok().build();
    }
}
~~~

Khi review, có thể nhận diện một số vấn đề:

- Controller tự quyết định quy tắc trạng thái và gán trạng thái trực tiếp.
- Quy tắc hủy chỉ được bảo vệ ở đường HTTP; tác vụ nền hoặc message handler có thể bỏ qua.
- Controller biết repository và chi tiết lưu trữ.
- Lời gọi email được thực hiện đồng bộ ngay trong request, khiến phản hồi phụ thuộc vào dịch vụ ngoài.
- Hợp đồng lỗi chưa rõ: đơn không tồn tại, không thể hủy và lỗi gửi email có thể bị trộn lẫn.
- Chưa thấy ranh giới transaction bao phủ thay đổi dữ liệu cần commit cùng nhau.

Một cách tổ chức rõ hơn:

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderController {
    private final CancelOrderService cancelOrder;

    public OrderController(CancelOrderService cancelOrder) {
        this.cancelOrder = cancelOrder;
    }

    @PostMapping("/{id}/cancellation")
    public ResponseEntity<Void> cancel(@PathVariable UUID id) {
        cancelOrder.execute(new OrderId(id));
        return ResponseEntity.noContent().build();
    }
}
~~~

Tầng ứng dụng điều phối use case:

~~~java
@Service
public class CancelOrderService {
    private final OrderRepository orders;
    private final OutboxRepository outbox;

    public CancelOrderService(
            OrderRepository orders,
            OutboxRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public void execute(OrderId id) {
        Order order = orders.findById(id)
                .orElseThrow(OrderNotFoundException::new);

        order.cancel();

        orders.save(order);
        outbox.save(OrderCancelledEvent.from(order));
    }
}
~~~

Mô hình nghiệp vụ bảo vệ chuyển trạng thái:

~~~java
public class Order {
    private OrderStatus status;

    public void cancel() {
        if (status != OrderStatus.DRAFT
                && status != OrderStatus.CONFIRMED) {
            throw new OrderCannotBeCancelledException(status);
        }

        status = OrderStatus.CANCELLED;
    }
}
~~~

Trong ví dụ, event được ghi vào outbox cùng transaction với thay đổi đơn hàng. Một publisher riêng gửi thông báo sau commit. Điều này giữ việc cập nhật đơn và ý định phát event nhất quán trong database, trong khi lời gọi mạng không nằm trong transaction của use case.

Các lớp và kiểu dữ liệu trong ví dụ là minh họa; dự án cần định nghĩa constructor, mapping, exception handler và quy tắc authorization cụ thể. Nếu việc hủy đơn còn yêu cầu hoàn tiền ở hệ thống thanh toán, đó là một bước phối hợp nhiều hệ thống với trạng thái và hành động bù phù hợp, không nên giả định có thể rollback cùng transaction database.

## 7. Kiểm tra hướng phụ thuộc

Một thiết kế dễ bảo trì thường có hướng phụ thuộc dễ giải thích. Tầng ngoài gọi khả năng của tầng trong; chi tiết lưu trữ triển khai hợp đồng mà ứng dụng cần. Quy tắc miền không nên phụ thuộc vào HTTP hoặc tên bảng database.

~~~mermaid
flowchart TD
    A["Presentation: Controller / DTO"] --> B["Application: Use case"]
    B --> C["Business: Domain model / policy"]
    B --> D["Repository port"]
    E["Data access adapter"] -. "implements" .-> D
    E --> F[("Database")]
~~~

Sơ đồ biểu diễn một cách tổ chức thường gặp. Vị trí khai báo repository interface có thể khác giữa các dự án; điểm cần review là application/domain không bị buộc phụ thuộc vào implementation JPA/JDBC cụ thể.

Những dấu hiệu cần xem xét:

- Domain model import `HttpServletRequest`, `ResponseEntity` hoặc kiểu DTO của controller.
- Application service tự tạo `EntityManager`, connection hoặc câu SQL.
- Repository gọi controller hoặc tạo HTTP response.
- Package phụ thuộc vòng, ví dụ application gọi data adapter trực tiếp trong khi adapter lại cần application service để hoàn tất truy vấn.
- Một tầng truy cập trực tiếp nhiều tầng khác nhau mà không có quy tắc rõ ràng.

Một số dự án dùng **closed layering**, trong đó tầng chỉ gọi tầng liền kề. Quy tắc này giúp hạn chế việc controller bỏ qua application service để gọi repository. Dự án khác dùng **open layering**, cho phép một tầng gọi xuyên qua tầng trung gian trong một số trường hợp có lý do, ví dụ query đọc đơn giản. Cả hai có thể hợp lý nếu quy tắc được thống nhất và không làm mờ quyền sở hữu.

Không nên đánh giá một thiết kế chỉ bằng số lần nhảy qua interface. Một abstraction có ích khi nó bảo vệ hợp đồng, tách lý do thay đổi hoặc tạo điểm kiểm thử. Nếu lớp trung gian chỉ chuyển tiếp tham số mà không có trách nhiệm rõ, nó có thể làm việc đọc mã khó hơn.

## 8. Những dấu hiệu thiết kế có vấn đề

| Dấu hiệu | Rủi ro | Hướng review |
|---|---|---|
| Fat controller | Giao thức, nghiệp vụ và lưu trữ trộn lẫn | Chuyển điều phối vào use case; đưa quy tắc vào mô hình phù hợp |
| Application service chứa mọi phép tính | Quy tắc miền phân tán trong các luồng use case | Xác định hành vi thuộc entity, value object hoặc domain service |
| Anemic model trong miền nhiều quy tắc | Trạng thái có thể bị thay đổi tùy tiện | Bảo vệ bất biến bằng hành vi có tên rõ |
| Repository quá tổng quát hoặc quá lớn | Caller khó hiểu truy vấn và trách nhiệm | Tổ chức hợp đồng theo nhu cầu truy cập có ý nghĩa |
| JPA entity đi xuyên mọi tầng | Schema và ORM ảnh hưởng API/domain | Cân nhắc DTO hoặc mapper tại ranh giới có lý do |
| Nhiều nơi cùng sửa trạng thái | Quy tắc bị sao chép, kết quả không nhất quán | Chỉ định nơi sở hữu chuyển trạng thái |
| Phụ thuộc vòng hoặc gọi vượt tầng tùy tiện | Khó kiểm thử và thay implementation | Kiểm tra hướng phụ thuộc và quy tắc closed/open |
| Một interface cho mọi thứ | Hợp đồng mơ hồ, abstraction phình to | Thu hẹp theo use case và khả năng caller cần |
| Tầng logic bị tách thành quá nhiều dịch vụ triển khai | Thêm độ trễ và chi phí vận hành không cần thiết | Xác minh lý do scale, deploy hoặc ownership độc lập |

Các dấu hiệu là tín hiệu để đặt câu hỏi, không phải kết luận tự động. Ví dụ, mô hình dữ liệu đơn giản có thể dùng getter/setter mà không gây hại. Một application service có thể chứa một phép tính nhỏ nếu đó là điều phối của ca sử dụng. Điều cần xem xét là độ phức tạp nghiệp vụ, số đường vào và khả năng thay đổi của hệ thống.

## 9. Quy trình review một thay đổi cụ thể

Review theo một thay đổi thực tế thường hiệu quả hơn kiểm tra package một cách trừu tượng. Có thể đi theo các bước:

1. **Lần theo luồng:** bắt đầu từ request, message hoặc job; theo đến nơi quyết định nghiệp vụ và nơi dữ liệu được lưu.
2. **Đánh dấu trách nhiệm:** với mỗi lớp, ghi nó nhận dữ liệu, điều phối, quyết định quy tắc hay thực hiện lưu trữ.
3. **Tìm nơi sở hữu quy tắc:** xác định bất biến và chuyển trạng thái quan trọng có một nơi bảo vệ hay đang bị lặp lại.
4. **Đọc hợp đồng:** xem kiểu đầu vào/đầu ra, exception, nullability, đơn vị và tác dụng phụ.
5. **Kiểm tra phụ thuộc:** xác định ai import hoặc gọi ai; tìm phụ thuộc ngược, vòng hoặc chi tiết framework bị rò rỉ.
6. **Kiểm tra transaction và side effect:** xác định thay đổi nào phải commit cùng nhau, lời gọi mạng nào xảy ra ngoài transaction và cách phục hồi.
7. **Đánh giá kiểm thử:** xem quy tắc được unit test ở đâu, hợp đồng được integration test thế nào và luồng giữa các tầng có được kiểm tra không.
8. **Đánh giá chi phí:** abstraction hoặc tầng mới có giải quyết vấn đề thực tế không, hay chỉ tăng số lớp và lần chuyển tiếp?

Khi review, hãy yêu cầu bằng chứng cụ thể: một phương thức đang chứa quy tắc nào, một kiểu dữ liệu đang làm rò rỉ chi tiết gì, hoặc một caller nào phụ thuộc vào hành vi ngầm. Nhận xét như “controller quá dày” chỉ hữu ích khi chỉ ra phần trách nhiệm nào đang thuộc về tầng khác và vì sao việc tách ra làm hợp đồng rõ hơn.

## 10. Checklist đánh giá trách nhiệm, hợp đồng và ownership

Có thể dùng checklist sau trong pull request hoặc buổi review kiến trúc:

- [ ] Mỗi thành phần có mục đích và lý do thay đổi tương đối rõ.
- [ ] Controller xử lý giao thức và chuyển đổi dữ liệu; không tự sở hữu quy tắc miền.
- [ ] Application service thể hiện trình tự ca sử dụng và các ranh giới công việc.
- [ ] Quy tắc và bất biến quan trọng được bảo vệ tại mô hình hoặc dịch vụ nghiệp vụ phù hợp.
- [ ] Repository/adapter đóng gói truy vấn và chi tiết lưu trữ.
- [ ] Hợp đồng đầu vào, đầu ra, lỗi và tác dụng phụ đủ rõ cho caller.
- [ ] Kiểu HTTP, JPA hoặc SQL không rò rỉ qua ranh giới nếu caller không cần chúng.
- [ ] Có nơi chịu trách nhiệm rõ cho mỗi chuyển trạng thái và nguồn dữ liệu có thẩm quyền.
- [ ] Hướng phụ thuộc không tạo vòng hoặc phụ thuộc ngược khó giải thích.
- [ ] Transaction chỉ bao phủ các thay đổi dữ liệu cần commit cùng nhau.
- [ ] Lời gọi mạng và side effect có cơ chế timeout, retry, idempotency hoặc phục hồi phù hợp.
- [ ] Có unit test cho quy tắc, integration test cho adapter và kiểm thử hợp đồng cho ranh giới quan trọng.
- [ ] Tầng hoặc dịch vụ triển khai mới có lý do rõ về scale, vận hành, bảo mật hoặc vòng đời phát hành.

Không cần mọi dự án áp dụng cùng một cấu trúc lớp hoặc cùng một bộ công nghệ. Checklist giúp nhóm phát hiện trách nhiệm mơ hồ, hợp đồng dễ vỡ và quyền sở hữu bị chia sẻ thiếu kiểm soát. Các ngoại lệ nên được giải thích bằng nhu cầu cụ thể của hệ thống.

## 11. Cách đưa ra nhận xét review có thể hành động

Một nhận xét tốt mô tả vị trí, tác động và hướng cải thiện. Ví dụ:

- **Chưa rõ:** “Logic này sai tầng.”
- **Cụ thể hơn:** “`OrderController.cancel()` tự kiểm tra trạng thái và đặt `CANCELLED`. Message handler có thể bỏ qua điều kiện này. Đề nghị đưa điều kiện chuyển trạng thái vào `Order.cancel()` để mọi đường gọi cùng tuân thủ bất biến.”

Hoặc:

- **Chưa rõ:** “Repository đang làm quá nhiều.”
- **Cụ thể hơn:** “`OrderRepository` đang quyết định có được hủy đơn hay không dựa trên trạng thái giao hàng. Đây là quy tắc nghiệp vụ; repository nên cung cấp dữ liệu cần thiết, còn use case/mô hình nghiệp vụ quyết định tính hợp lệ.”

Hoặc:

- **Chưa rõ:** “DTO chưa tốt.”
- **Cụ thể hơn:** “Response hiện trả `OrderJpaEntity` và làm lộ tên quan hệ JPA cùng các trường nội bộ. Một `OrderResponse` riêng sẽ giúp API giữ hợp đồng ổn định khi schema hoặc mapping thay đổi.”

Nhận xét review nên phân biệt lỗi thực tế với đề xuất phong cách. Nếu thiết kế hiện tại đáp ứng hợp đồng, dễ kiểm thử và không có rủi ro thay đổi đáng kể, không cần yêu cầu tái cấu trúc chỉ để giống một sơ đồ mẫu.

## 12. Nguyên tắc kết luận khi đánh giá thiết kế phân tầng

Một thiết kế phân tầng tốt giúp người đọc trả lời được: dữ liệu đi vào ở đâu, ca sử dụng được điều phối ở đâu, quy tắc được bảo vệ ở đâu, và chi tiết lưu trữ được thực hiện ở đâu. Hợp đồng giữa các tầng cần diễn đạt đúng nhu cầu của caller; quyền sở hữu trạng thái và quy tắc phải đủ rõ để tránh nhiều thành phần cùng quyết định một việc.

Khi review, hãy ưu tiên những vấn đề có ảnh hưởng đến tính đúng đắn, khả năng thay đổi, kiểm thử và vận hành. Không có một số tầng, một kiểu repository hay một mức độ DDD bắt buộc cho mọi hệ thống. Điều cần đạt là trách nhiệm có chủ đích, hợp đồng có thể hiểu và phụ thuộc có thể giải thích. Nếu một tầng mới hoặc abstraction mới không làm rõ một trong những điều đó, hãy xem xét liệu độ phức tạp bổ sung có thực sự cần thiết hay không.

