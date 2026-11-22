# Phân biệt kiểm toán dữ liệu, log HTTP và nhật ký nghiệp vụ

Trong một ứng dụng Spring Data REST, kiểm toán dữ liệu, log HTTP và nhật ký nghiệp vụ đều có thể ghi nhận hoạt động, nhưng chúng trả lời những câu hỏi khác nhau. Kiểm toán dữ liệu cho biết ai tạo hoặc sửa một bản ghi và thời điểm nào; log HTTP cho biết request nào đã đi qua hệ thống và server phản hồi ra sao; nhật ký nghiệp vụ ghi lại hành động có ý nghĩa với domain, chẳng hạn đơn hàng được xác nhận hoặc hạn mức được thay đổi vì một lý do cụ thể.

Ba loại thông tin này bổ sung cho nhau. Dùng đúng loại ở đúng tầng giúp điều tra sự cố, đáp ứng yêu cầu truy vết và giải thích lịch sử nghiệp vụ mà không biến một dòng log kỹ thuật thành bằng chứng đầy đủ về một quyết định kinh doanh.

## 1. Ba loại bản ghi trả lời ba câu hỏi khác nhau

| Loại | Câu hỏi chính | Ví dụ |
|---|---|---|
| Kiểm toán dữ liệu (data auditing) | Ai tạo hoặc cập nhật bản ghi? Bản ghi được tạo/cập nhật lúc nào? | createdBy=alice, createdDate=2026-11-11T08:00Z, lastModifiedBy=bob. |
| Log HTTP (HTTP/access logging) | Client gọi endpoint nào, khi nào, mất bao lâu và nhận status gì? | POST /api/orders trả về 201, thời gian xử lý 84 ms, requestId=abc123. |
| Nhật ký nghiệp vụ (business journal) | Hành động nghiệp vụ nào đã xảy ra, ai thực hiện, đối tượng nào bị ảnh hưởng và vì sao? | Đơn hàng 42 được xác nhận bởi alice, từ DRAFT sang CONFIRMED, lý do khách đã thanh toán. |

Ví dụ, một người dùng xác nhận đơn hàng:

- Data auditing có thể cập nhật lastModifiedBy và lastModifiedDate trên entity PurchaseOrder.
- HTTP log ghi nhận request POST /api/orders/42/confirm, status 200 và thời gian xử lý.
- Business journal ghi sự kiện OrderConfirmed với orderId=42, actor=alice, trạng thái trước/sau và lý do xác nhận.

Nếu chỉ có data auditing, ta biết bản ghi đã được sửa nhưng không biết chính xác nghiệp vụ gì đã diễn ra. Nếu chỉ có HTTP log, ta biết endpoint được gọi nhưng không chắc thay đổi nào đã được commit. Nếu chỉ có business journal, ta có thể biết sự kiện nghiệp vụ nhưng thiếu thông tin request, latency hoặc lỗi ở tầng HTTP.

## 2. Kiểm toán dữ liệu với Spring Data JPA Auditing

Spring Data JPA Auditing giúp tự động điền metadata phổ biến lên entity:

- @CreatedBy: người tạo bản ghi.
- @CreatedDate: thời điểm tạo bản ghi.
- @LastModifiedBy: người cập nhật gần nhất.
- @LastModifiedDate: thời điểm cập nhật gần nhất.

Các trường này thường được lưu cùng entity và phản ánh trạng thái kiểm toán hiện tại. Chúng không tự tạo lịch sử đầy đủ của mọi lần sửa; lastModifiedBy và lastModifiedDate sẽ được cập nhật ở lần thay đổi tiếp theo.

Ví dụ entity:

~~~java
import java.time.Instant;

import jakarta.persistence.Entity;
import jakarta.persistence.EntityListeners;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

@Entity
@EntityListeners(AuditingEntityListener.class)
public class PurchaseOrder {

    @Id
    @GeneratedValue
    private Long id;

    private String status;

    @CreatedBy
    private String createdBy;

    @CreatedDate
    private Instant createdDate;

    @LastModifiedBy
    private String lastModifiedBy;

    @LastModifiedDate
    private Instant lastModifiedDate;

    // getters and setters
}
~~~

Để bật auditing, cấu hình @EnableJpaAuditing và cung cấp AuditorAware để Spring biết người dùng hiện tại:

~~~java
@Configuration
@EnableJpaAuditing(auditorAwareRef = "auditorProvider")
public class JpaAuditingConfiguration {

    @Bean
    AuditorAware<String> auditorProvider() {
        return () -> {
            Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

            if (authentication == null
                    || !authentication.isAuthenticated()
                    || authentication instanceof AnonymousAuthenticationToken) {
                return Optional.empty();
            }

            return Optional.of(authentication.getName());
        };
    }
}
~~~

Ví dụ trên lấy tên principal từ Spring Security. Trong ứng dụng thực tế, hãy dùng định danh người dùng ổn định như user ID thay vì display name có thể thay đổi. Với tác vụ chạy nền, có thể trả về một định danh hệ thống riêng hoặc quy định rõ trường auditor được để trống; không nên gán nhầm tác vụ nền cho người dùng cuối.

Auditing cần được áp dụng nhất quán cho entity: bật cấu hình, gắn AuditingEntityListener hoặc cấu hình tương đương, khai báo các trường metadata và bảo đảm AuditorAware trả về đúng actor. Nếu không có người dùng xác thực, cần quyết định rõ cách biểu diễn actor thay vì giả định luôn có Authentication.

## 3. Auditing cho biết ai sửa gần nhất, không lưu toàn bộ lịch sử

Giả sử một đơn hàng được cập nhật ba lần:

| Lần thay đổi | Người thực hiện | Trạng thái |
|---|---|---|
| Tạo mới | alice | DRAFT |
| Cập nhật địa chỉ | bob | DRAFT |
| Xác nhận | carol | CONFIRMED |

Sau lần cuối, các trường @CreatedBy và @CreatedDate vẫn cho biết ai tạo bản ghi ban đầu. @LastModifiedBy và @LastModifiedDate chỉ cho biết người sửa gần nhất và thời điểm gần nhất.

Chúng không giữ lại đầy đủ rằng bob đã đổi địa chỉ, carol đã xác nhận đơn hàng, hoặc giá trị trước/sau của từng trường. Nếu cần lịch sử đó, cần một business journal, audit table lưu từng phiên bản, hoặc cơ chế lưu lịch sử phù hợp với yêu cầu.

Có thể mở rộng auditing bằng các trường domain riêng, nhưng không nên biến các trường metadata hiện tại thành nơi chứa một chuỗi lịch sử nối tiếp. Lịch sử cần có cấu trúc riêng để truy vấn, đối chiếu và bảo vệ tính toàn vẹn.

## 4. Log HTTP ghi nhận request và response

HTTP/access log tập trung vào giao tiếp giữa client và server. Các trường thường hữu ích gồm:

- Thời điểm request bắt đầu hoặc kết thúc.
- HTTP method và route/path.
- Status code.
- Thời gian xử lý.
- Client address nếu chính sách cho phép.
- Request ID hoặc trace ID để nối log giữa gateway, ứng dụng và dịch vụ khác.
- User ID hoặc principal đã xác thực nếu cần điều tra và chính sách dữ liệu cho phép.

Ví dụ một dòng access log:

~~~text
2026-11-11T08:15:32Z requestId=abc123 method=POST
path=/api/orders/42/confirm status=200 durationMs=84
principal=user-17
~~~

Log này cho biết request đã được xử lý và trả về 200. Nó không chứng minh rằng một sự kiện OrderConfirmed đã được ghi bền vững trong database, cũng không mô tả trạng thái nghiệp vụ trước và sau.

Trong Spring Boot, có thể bật access log của embedded Tomcat bằng cấu hình server:

~~~properties
server.tomcat.accesslog.enabled=true
server.tomcat.accesslog.directory=logs
server.tomcat.accesslog.pattern=%t %a "%r" %s %D
~~~

Cấu hình cụ thể phụ thuộc embedded server. Nếu ứng dụng chạy sau reverse proxy hoặc API gateway, access log ở proxy cũng hữu ích để ghi nhận request ở ranh giới mạng; hãy truyền request/trace ID qua các tầng để đối chiếu.

Nếu cần log ở tầng ứng dụng, có thể dùng OncePerRequestFilter hoặc interceptor để bổ sung correlation ID, principal và metadata theo chuẩn chung. Hãy đo thời gian bằng cơ chế phù hợp và ghi status sau khi response được xử lý. Tránh ghi toàn bộ request/response body theo mặc định.

## 5. Bảo vệ dữ liệu trong HTTP log

HTTP log thường chứa dữ liệu đến từ client và có thể vô tình ghi lại bí mật. Không nên ghi trực tiếp:

- Authorization header, access token, refresh token hoặc cookie phiên.
- Mật khẩu, API key, mã xác thực dùng một lần.
- Số thẻ, thông tin thanh toán hoặc dữ liệu cá nhân không cần thiết.
- Query parameter có thể chứa thông tin nhạy cảm.
- Toàn bộ request body chỉ để tiện debug.

Nên ưu tiên route template thay cho URL đầy đủ có ID hoặc query nhạy cảm nếu không cần thiết. Ví dụ log /api/orders/{id}/confirm thay cho đường dẫn thực tế có ID khi chính sách yêu cầu giảm dữ liệu nhận dạng.

Cần có chính sách retention, phân quyền đọc log, mã hóa nơi lưu trữ và quy trình xóa dữ liệu hết hạn. Log phải đủ để điều tra nhưng không trở thành kho lưu trữ bí mật thứ hai.

## 6. Nhật ký nghiệp vụ ghi lại sự kiện có ý nghĩa với domain

Business journal là lịch sử các hành động hoặc sự kiện nghiệp vụ đã xảy ra. Một bản ghi thường cần các thông tin:

- eventId duy nhất.
- eventType, ví dụ OrderConfirmed hoặc RefundIssued.
- aggregateType và aggregateId để xác định đối tượng nghiệp vụ.
- actorId hoặc systemActor.
- occurredAt: thời điểm nghiệp vụ xảy ra.
- dữ liệu liên quan như trạng thái trước/sau, số tiền, lý do hoặc nguồn yêu cầu.
- correlationId/requestId để nối với HTTP log.
- version hoặc sequence nếu cần sắp thứ tự sự kiện của cùng aggregate.

Ví dụ một sự kiện:

~~~json
{
  "eventId": "evt-8f31",
  "eventType": "OrderConfirmed",
  "aggregateType": "PurchaseOrder",
  "aggregateId": "42",
  "actorId": "user-17",
  "occurredAt": "2026-11-11T08:15:32Z",
  "data": {
    "previousStatus": "DRAFT",
    "newStatus": "CONFIRMED",
    "reason": "Payment received"
  },
  "correlationId": "abc123"
}
~~~

Đây là bản ghi diễn tả một hành động nghiệp vụ cụ thể. Nó có thể được dùng để tra cứu lịch sử, giải thích vì sao trạng thái thay đổi, phục vụ hỗ trợ khách hàng hoặc tạo báo cáo tuân thủ.

Business journal nên ưu tiên các event có tên thể hiện điều đã xảy ra, ví dụ OrderConfirmed, AddressChanged hoặc RefundApproved. Tránh ghi những mô tả quá chung như EntityUpdated vì chúng không giải thích ý nghĩa nghiệp vụ.

## 7. Ghi business journal cùng transaction với thay đổi dữ liệu

Nếu thay đổi đơn hàng được commit nhưng bản ghi journal không được lưu, lịch sử sẽ thiếu sự kiện. Ngược lại, nếu journal được ghi nhưng thay đổi đơn hàng rollback, journal có thể mô tả một hành động chưa thực sự xảy ra.

Với nghiệp vụ quan trọng, có thể ghi entity và business journal trong cùng transaction cơ sở dữ liệu:

~~~java
@Service
public class OrderService {

    private final PurchaseOrderRepository orders;
    private final BusinessJournalRepository journal;

    public OrderService(
            PurchaseOrderRepository orders,
            BusinessJournalRepository journal) {
        this.orders = orders;
        this.journal = journal;
    }

    @Transactional
    public void confirm(Long orderId, String actorId, String reason) {
        PurchaseOrder order = orders.findById(orderId)
            .orElseThrow(() -> new EntityNotFoundException("Order not found"));

        String previousStatus = order.getStatus();

        if (!"DRAFT".equals(previousStatus)) {
            throw new IllegalStateException("Order cannot be confirmed");
        }

        order.setStatus("CONFIRMED");

        journal.save(BusinessJournalEntry.orderConfirmed(
            order.getId(),
            actorId,
            previousStatus,
            "CONFIRMED",
            reason,
            Instant.now()
        ));
    }
}
~~~

Trong ví dụ, thay đổi trạng thái và bản ghi journal tham gia cùng transaction. Nếu transaction rollback, cả hai thay đổi database đều rollback. Repository save cho journal được minh họa qua factory method để giữ cấu trúc domain của event rõ ràng.

Nếu cần gửi message tới hệ thống bên ngoài sau commit, không nên gọi dịch vụ từ xa trực tiếp giữa transaction và kỳ vọng hai hệ thống luôn đồng bộ. Transactional outbox là một lựa chọn: ghi outbox record cùng transaction với thay đổi nghiệp vụ, sau đó một publisher đọc outbox và gửi message có retry. Cách này giảm nguy cơ database đã commit nhưng message bị mất do lỗi mạng.

## 8. Spring Data REST repository events có vai trò gì?

Spring Data REST cung cấp các event như BeforeCreateEvent, AfterCreateEvent, BeforeSaveEvent, AfterSaveEvent, BeforeDeleteEvent và AfterDeleteEvent. Có thể xử lý chúng bằng @RepositoryEventHandler để chạy logic quanh vòng đời lưu entity được thực hiện qua repository REST.

Ví dụ:

~~~java
@Component
@RepositoryEventHandler(PurchaseOrder.class)
public class PurchaseOrderEventHandler {

    @HandleBeforeSave
    public void beforeSave(PurchaseOrder order) {
        if ("CANCELLED".equals(order.getStatus())
                && order.getItems().isEmpty()) {
            throw new IllegalStateException(
                "Không thể hủy đơn hàng chưa có sản phẩm"
            );
        }
    }

    @HandleAfterSave
    public void afterSave(PurchaseOrder order) {
        // Hook cho xử lý sau khi repository save event xảy ra.
    }
}
~~~

Các repository event hữu ích cho validation hoặc xử lý kỹ thuật gắn với persistence. Tuy nhiên, BeforeSaveEvent/AfterSaveEvent không tự cho biết ý định nghiệp vụ là “xác nhận đơn”, “đổi địa chỉ” hay “áp dụng giảm giá”. Nếu cần business journal có ý nghĩa, hãy ghi event rõ ràng tại service hoặc use case nơi biết actor, lý do và quyết định nghiệp vụ.

Ngoài ra, AfterSaveEvent là event sau thao tác repository save, không nên mặc định nó có nghĩa transaction đã commit. Với tác vụ cần chạy sau commit, dùng transaction synchronization phù hợp, @TransactionalEventListener(AFTER_COMMIT) hoặc outbox theo yêu cầu độ tin cậy.

Các thao tác được thực hiện ngoài luồng Spring Data REST, ví dụ service nội bộ, batch job hoặc message consumer, có thể không đi qua cùng repository event handler. Vì vậy, không dùng repository event như cơ chế duy nhất để ghi nhận toàn bộ lịch sử nghiệp vụ của hệ thống.

## 9. So sánh nơi lưu và thời gian lưu

| Tiêu chí | Data auditing | HTTP log | Business journal |
|---|---|---|---|
| Vị trí thường dùng | Các cột metadata trên entity. | File, log platform, gateway hoặc hệ thống quan sát. | Bảng journal, event store hoặc outbox/archive. |
| Đơn vị ghi | Entity được tạo/cập nhật. | Một request/response hoặc một lần truy cập. | Một sự kiện nghiệp vụ. |
| Mức ý nghĩa | Ai tạo/sửa và thời điểm gần nhất. | Giao tiếp kỹ thuật và kết quả HTTP. | Hành động, actor, đối tượng và lý do. |
| Lịch sử nhiều lần | Không tự lưu mọi phiên bản. | Có nhiều request nhưng không nhất thiết phản ánh commit. | Có thể lưu từng sự kiện theo thời gian. |
| Truy vấn điển hình | Ai sửa bản ghi này lần cuối? | Request nào trả 500? Endpoint nào chậm? | Vì sao đơn hàng chuyển sang CONFIRMED? |
| Yêu cầu bảo vệ | Kiểm soát cập nhật metadata. | Bảo vệ log, giới hạn dữ liệu nhạy cảm. | Hạn chế sửa/xóa, phân quyền và lưu giữ. |

Không nhất thiết phải dùng một kho lưu trữ cho cả ba. Data auditing thường nằm cùng entity để dễ đọc trạng thái hiện tại; HTTP log thường ở hệ thống logging tập trung; business journal thường ở persistence riêng có khả năng truy vấn theo entity, actor và event type.

## 10. Thiết kế correlation ID để nối ba nguồn

Khi điều tra một thao tác, cần nối được request, thay đổi entity và sự kiện nghiệp vụ. Correlation ID hoặc trace ID có thể đóng vai trò khóa liên kết:

1. Gateway hoặc ứng dụng tạo/nhận request ID khi request bắt đầu.
2. HTTP log ghi request ID cùng method, route, status và duration.
3. Service truyền request ID vào business journal entry.
4. Nếu có message hoặc tác vụ nền, đưa correlation ID vào message header hoặc metadata.
5. Data auditing lưu actor và timestamp trên entity; khi cần, có thể truy vấn entity theo ID và đối chiếu với journal.

Ví dụ, tìm requestId=abc123 trong HTTP log sẽ cho biết request nào đã đến. Từ cùng correlationId, tìm business journal để xem OrderConfirmed được ghi hay không. Sau đó đọc PurchaseOrder 42 để xác nhận trạng thái hiện tại và metadata lastModified.

Không nên dùng request ID làm định danh duy nhất của sự kiện nghiệp vụ: một request có thể phát sinh nhiều sự kiện, và một sự kiện có thể được xử lý qua nhiều message hoặc bước nội bộ. Hãy có eventId riêng và dùng correlationId chỉ để liên kết luồng xử lý.

## 11. Bảo đảm tính toàn vẹn và khả năng truy vết

Nếu business journal phục vụ kiểm toán hoặc tranh chấp, cần xác định rõ ai được đọc, ai được ghi và có được phép sửa/xóa hay không. Một số biện pháp thường dùng:

- Chỉ cho phép service chuyên trách tạo journal entry.
- Không cung cấp API cập nhật/xóa journal cho người dùng thông thường.
- Lưu actor ID và thời gian theo nguồn đáng tin cậy của server.
- Giữ event ID duy nhất và khóa tham chiếu tới aggregate.
- Ghi lý do hoặc nguồn thay đổi khi nghiệp vụ yêu cầu.
- Dùng transaction/outbox để tránh journal bị lệch so với dữ liệu chính.
- Thiết lập retention, backup và phân quyền đọc phù hợp.
- Nếu yêu cầu chống sửa đổi rất cao, cân nhắc cơ chế append-only, kiểm soát quyền ở database, hash chain hoặc lưu trữ bất biến phù hợp chính sách.

Không nên cho client tự gửi actorId tùy ý rồi tin giá trị đó làm người thực hiện. Actor cần được lấy từ principal đã xác thực hoặc danh tính hệ thống được kiểm soát. Dữ liệu trước/sau cũng nên được lấy từ entity trong service thay vì tin toàn bộ nội dung do client khai báo.

## 12. Quy trình kiểm tra ba cơ chế

Với endpoint xác nhận đơn hàng, có thể kiểm tra từng loại bản ghi:

1. Tạo đơn hàng bằng POST; xác nhận @CreatedBy và @CreatedDate được điền.
2. Cập nhật đơn hàng bằng PUT/PATCH; xác nhận @LastModifiedBy và @LastModifiedDate thay đổi.
3. Gọi endpoint xác nhận đơn hàng; xác nhận HTTP log ghi method, route, status, duration và request ID.
4. Xác nhận business journal có event OrderConfirmed với actor, order ID, trạng thái trước/sau và lý do.
5. Dùng correlation ID để tìm request trong HTTP log và sự kiện trong journal.
6. Gây lỗi validation hoặc lỗi nghiệp vụ; xác nhận request lỗi được log nhưng không tạo business event thành công.
7. Mô phỏng rollback; xác nhận thay đổi entity và journal cùng transaction đều không được commit.
8. Kiểm tra quyền đọc log/journal và xác nhận token, mật khẩu hoặc dữ liệu nhạy cảm không xuất hiện trong log.

## 13. Chọn cơ chế theo nhu cầu

- Muốn biết ai tạo và ai sửa bản ghi gần nhất: dùng Spring Data JPA Auditing.
- Muốn biết request nào tới endpoint, status và thời gian xử lý: dùng HTTP/access log.
- Muốn giải thích hành động nghiệp vụ, lý do và lịch sử thay đổi: ghi business journal.
- Muốn điều tra xuyên nhiều service: thêm correlation/trace ID.
- Muốn bảo đảm sự kiện nghiệp vụ được phát sau commit: dùng AFTER_COMMIT hoặc transactional outbox.
- Muốn lưu lịch sử mọi lần thay đổi field: thiết kế audit history/version table hoặc event journal; bốn trường auditing hiện tại là chưa đủ.

Kiểm toán dữ liệu, log HTTP và nhật ký nghiệp vụ cùng phục vụ khả năng truy vết nhưng ở ba mức khác nhau. Hãy dùng auditing để lưu metadata của entity, HTTP log để quan sát request/response, và business journal để ghi các sự kiện có ý nghĩa domain. Kết nối chúng bằng actor ID, entity ID và correlation ID sẽ giúp trả lời đầy đủ ai đã làm gì, request nào kích hoạt và trạng thái nghiệp vụ thay đổi ra sao.
