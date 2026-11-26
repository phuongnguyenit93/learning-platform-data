# Phân quyền publish

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, application events cho phép module công bố sự thật nghiệp vụ để các module khác phản ứng mà không cần phụ thuộc trực tiếp vào implementation của nhau. Tuy nhiên, khả năng gọi `publishEvent` không đồng nghĩa với quyền được phép công bố mọi sự kiện. Một ứng dụng an toàn cần xác định ai được yêu cầu hành động nghiệp vụ, module nào sở hữu sự thật được phát ra, tiến trình nào được gửi message đến broker và đích nhận nào được phép tiếp nhận.

Phân quyền publish cần được thực hiện ở đúng ranh giới. Quyền của người dùng hoặc caller được kiểm tra trước khi thực hiện command; quyền sở hữu event được giữ trong kiến trúc module; publisher service identity được giới hạn khi gửi ra broker; broker ACL kiểm soát producer nào được ghi vào destination nào. Các lớp này bổ sung cho nhau và không thay thế lẫn nhau.

## 1. Phân biệt xác thực và phân quyền

**Authentication (xác thực)** trả lời câu hỏi caller là ai. **Authorization (phân quyền)** quyết định caller đó có được phép thực hiện hành động cụ thể trên tài nguyên cụ thể hay không.

Ví dụ, một nhân viên đã đăng nhập có thể được xác thực thành công nhưng không có quyền xác nhận mọi đơn hàng. Quyền có thể phụ thuộc vào:

- Authority hoặc role được cấp.
- Người dùng có thuộc tenant sở hữu đơn hàng hay không.
- Người dùng có phải chủ đơn hoặc thành viên nhóm xử lý đơn hay không.
- Trạng thái hiện tại của đơn có cho phép xác nhận hay không.
- Hành động có nằm trong phạm vi nghiệp vụ và hạn mức được giao hay không.

Không nên dùng một role chung như `USER` để cho phép publish tất cả event. Quyền cần gắn với hành động nghiệp vụ và phạm vi tài nguyên. Ví dụ `order:confirm` có thể cho phép yêu cầu xác nhận đơn; nó không tự động cấp quyền phát PaymentCaptured hoặc InvoiceIssued.

Cũng cần phân biệt quyền nghiệp vụ với quyền kỹ thuật của broker. Người dùng có thể được phép xác nhận đơn qua API nhưng không cần có credential RabbitMQ hoặc Kafka. Ứng dụng kiểm tra quyền người dùng rồi dùng service identity riêng để phát message.

## 2. Xác định ai có quyền công bố từng loại event

Mỗi event nên có một module sở hữu và một điều kiện phát rõ ràng. Module sở hữu là nơi nắm dữ liệu và quy tắc domain quyết định sự thật đó có xảy ra hay không.

Ví dụ:

| Event | Module sở hữu | Điều kiện công bố |
|---|---|---|
| OrderConfirmed | Orders | Đơn hàng chuyển sang trạng thái được xác nhận hợp lệ |
| PaymentCaptured | Payments | Nhà cung cấp thanh toán xác nhận đã thu tiền |
| InventoryReserved | Inventory | Reservation đã được ghi nhận thành công |
| InvoiceIssued | Invoicing | Hóa đơn đã được phát hành theo quy tắc domain |
| ShipmentDispatched | Shipping | Lô hàng đã được bàn giao cho đơn vị vận chuyển |

Module khác có thể phát command hoặc yêu cầu module sở hữu thực hiện hành động, nhưng không nên tự tạo event để tuyên bố một sự thật thuộc quyền quyết định của module khác.

Spring Modulith hỗ trợ tổ chức ranh giới module và kiểm tra một số quy tắc phụ thuộc kiến trúc. Ranh giới module giúp xác định nơi sở hữu event và API được phép gọi. Tuy nhiên, ranh giới module không tự động là cơ chế authorization runtime cho từng người dùng hoặc từng lần gọi `ApplicationEventPublisher`. Ứng dụng vẫn cần kiểm tra quyền ở application service và bảo vệ broker ở lớp transport.

## 3. Kiểm tra quyền trước khi phát application event

Quyền của caller cần được kiểm tra tại application service xử lý command. Khi quyền bị từ chối, thao tác domain không được thực hiện và event tương ứng không được phát.

Ví dụ dùng Spring Security method security:

~~~java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
~~~

Application service kiểm tra quyền xác nhận đơn trước khi thay đổi trạng thái và phát event:

~~~java
@Service
class ConfirmOrderService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;

    ConfirmOrderService(
        OrderRepository orders,
        ApplicationEventPublisher events
    ) {
        this.orders = orders;
        this.events = events;
    }

    @PreAuthorize("@orderAuthorization.canConfirm(authentication, #orderId)")
    @Transactional
    public void confirm(UUID orderId) {
        Order order = orders.findById(orderId)
            .orElseThrow(OrderNotFoundException::new);

        order.confirm();

        events.publishEvent(new OrderConfirmed(
            UUID.randomUUID(),
            order.id(),
            order.version()
        ));
    }
}
~~~

`OrderAuthorization` là policy bean của ứng dụng, kiểm tra cả quyền hành động lẫn phạm vi truy cập tài nguyên. Ví dụ, policy có thể xác nhận người dùng có authority `order:confirm` và đơn hàng thuộc tenant mà người dùng được phép thao tác.

Không nên chỉ kiểm tra role ở controller rồi giả định mọi caller đều đi qua controller đó. Application service có thể được gọi từ REST endpoint, scheduler, message listener hoặc một module khác. Đặt authorization tại ranh giới xử lý command giúp mọi đường gọi đều đi qua cùng chính sách.

Lưu ý `@PreAuthorize` hoạt động thông qua Spring proxy. Lời gọi nội bộ kiểu self-invocation có thể bỏ qua proxy và không chạy method security. Những đường gọi nội bộ cần được thiết kế để đi qua bean được bảo vệ hoặc thực hiện policy check tường minh.

## 4. Phân biệt quyền caller với quy tắc domain

Authorization xác định ai được phép yêu cầu một hành động. Domain invariant xác định hành động đó có hợp lệ với trạng thái nghiệp vụ hiện tại hay không. Cả hai đều cần được kiểm tra.

Ví dụ, một nhân viên có quyền `order:confirm` nhưng đơn hàng đã bị hủy. Người dùng được phép thực hiện hành động nói chung, song đơn cụ thể không còn đủ điều kiện để xác nhận.

Một quy trình phù hợp:

1. Xác thực caller và xác định tenant/identity.
2. Kiểm tra authority và quyền trên tài nguyên.
3. Tải aggregate từ module sở hữu.
4. Thực thi domain method để kiểm tra trạng thái và invariant.
5. Ghi thay đổi trong transaction.
6. Phát application event biểu đạt kết quả đã xảy ra.

Không phát event trước khi domain chấp nhận chuyển trạng thái. Ví dụ, không phát OrderConfirmed chỉ vì caller có quyền yêu cầu xác nhận; event chỉ được phát sau khi `order.confirm()` thành công và thay đổi được commit theo transaction model đã cấu hình.

## 5. Không cho caller tự chọn event type để publish

Một API nguy hiểm là nhận tên event, class hoặc routing destination từ request rồi chuyển thẳng đến publisher:

~~~java
// Không dùng dữ liệu caller để chọn tùy ý event class hoặc destination.
publisher.publish(request.eventType(), request.payload());
~~~

Nếu caller có thể tự chọn `eventType`, destination hoặc routing key, họ có thể giả mạo sự thật thuộc module khác, phát event không được phép hoặc gửi dữ liệu đến consumer ngoài dự kiến.

Thay vào đó:

- API nhận command nghiệp vụ có schema cụ thể, ví dụ ConfirmOrderRequest.
- Application service quyết định event nào được phát sau khi xử lý command.
- Event type được ánh xạ từ code đã kiểm soát, không lấy trực tiếp từ input.
- Destination và routing key được cấu hình theo allow-list.
- Payload được tạo từ dữ liệu domain đã xác minh.
- Caller không được truyền tùy ý tên class Java, exchange, topic hoặc queue.

Nếu hệ thống cần một publisher facade dùng chung, facade nên nhận các kiểu event đã đăng ký và kiểm tra module/destination được phép. Tuy nhiên, facade không thay thế authorization trên command và domain ownership.

## 6. Quyền publish của service identity

Khi externalize event, ứng dụng kết nối đến broker bằng credential của một service identity. Credential này đại diện cho workload hoặc publisher, không đại diện cho người dùng cuối đang đăng nhập.

Nên cấp identity riêng cho từng ứng dụng hoặc nhóm publisher có cùng trách nhiệm. Ví dụ:

- Orders publisher chỉ có quyền ghi vào exchange/topic dành cho event đơn hàng.
- Payments publisher chỉ có quyền ghi event thanh toán.
- Inventory consumer chỉ có quyền đọc queue dành cho Inventory.
- Một service chỉ quản lý topology khi thật sự cần quyền configure.

Không dùng một tài khoản broker dùng chung có toàn quyền cho tất cả service. Khi một credential bị lộ, phạm vi ảnh hưởng cần được giới hạn trong đúng destination mà workload đó phải sử dụng.

Service identity cần được quản lý như một danh tính workload:

- Lưu credential trong secret manager hoặc nền tảng quản lý secret.
- Dùng TLS cho kết nối broker qua mạng.
- Luân chuyển credential theo quy trình có kiểm soát.
- Thu hồi quyền hoặc credential khi service ngừng hoạt động.
- Không ghi username/password, token hoặc private key vào event payload và log.
- Tách credential giữa môi trường development, staging và production.

Nếu sử dụng workload identity, client certificate hoặc cơ chế xác thực service-to-service, hãy xác định rõ cách ánh xạ danh tính đó sang quyền publish ở broker.

## 7. Giới hạn quyền tại RabbitMQ và Kafka

Broker là lớp thực thi quyền đối với message được publish. Ứng dụng có thể kiểm tra quyền caller đúng nhưng vẫn cần broker từ chối một publisher bị cấu hình sai hoặc credential bị sử dụng trái phép.

### RabbitMQ

RabbitMQ quản lý quyền theo virtual host và các quyền configure, write, read. Publisher thường chỉ cần quyền write lên exchange được phép. Nó không cần quyền configure để tạo/xóa exchange hoặc queue, và cũng không cần quyền read queue nếu chỉ gửi message.

Nên:

- Tách virtual host theo môi trường hoặc ranh giới tin cậy khi phù hợp.
- Cấp write permission đúng exchange cho publisher.
- Giới hạn configure permission cho thành phần quản lý topology.
- Cấp read permission đúng queue cho consumer.
- Dùng topic permission hoặc cơ chế kiểm soát routing phù hợp nếu cần giới hạn routing key.
- Kiểm tra quyền thực tế bằng credential của từng service.

Không cấp quyền rộng trên toàn virtual host chỉ để một publisher gửi được một loại event.

### Apache Kafka

Với Kafka, ACL có thể giới hạn principal được phép ghi vào topic cụ thể. Producer cần quyền Write trên topic và các quyền bổ sung chỉ khi cấu hình hoặc tính năng đang dùng yêu cầu.

Nên:

- Dùng principal riêng cho mỗi producer.
- Chỉ cấp Write trên topic mà producer sở hữu.
- Chỉ cấp Read cho consumer group/topic phù hợp.
- Giới hạn quyền Create topic và Alter topic cho tài khoản vận hành.
- Dùng TLS/SASL hoặc cơ chế xác thực workload phù hợp với cluster.
- Không để producer có quyền ghi vào mọi topic chỉ vì dùng chung cluster.

Tên quyền và cấu hình ACL cụ thể phụ thuộc phiên bản broker, security plugin và mô hình triển khai. Hãy kiểm tra policy thực tế trên cluster.

## 8. Phân quyền theo tenant và dữ liệu event

Trong hệ thống multi-tenant, quyền publish cần bảo đảm caller chỉ thao tác trong tenant được phép. Không tin tenant ID do client tự gửi nếu chưa đối chiếu với identity đã xác thực.

Ví dụ, policy cần kiểm tra:

- Principal có quyền `order:confirm`.
- Order thuộc tenant mà principal được phép truy cập.
- Tenant trong request khớp tenant sở hữu aggregate.
- Event được tạo với tenant ID lấy từ dữ liệu đã xác minh.
- Consumer tiếp tục áp dụng tenant boundary khi đọc hoặc cập nhật dữ liệu.

Tenant ID trong payload chỉ là metadata để định tuyến và xử lý. Nó không phải bằng chứng authorization. Consumer không được tin một event chỉ vì payload chứa tenant ID hoặc actor ID hợp lệ về cú pháp.

Chỉ đưa vào event metadata định danh cần thiết như actorId, tenantId, correlationId và causationId. Không đưa access token, cookie, session object hoặc toàn bộ SecurityContext vào event. Những thông tin xác thực đó có thể hết hạn, bị lộ hoặc không còn ý nghĩa khi event được xử lý sau nhiều phút.

## 9. Bối cảnh bất đồng bộ và danh tính người thực hiện

Khi listener chạy bất đồng bộ hoặc được phục hồi sau restart, SecurityContext của request ban đầu có thể không còn tồn tại. Không nên phụ thuộc vào thread-local SecurityContext để quyết định quyền cho một công việc đã được xếp hàng.

Hãy phân biệt hai câu hỏi:

1. Caller ban đầu có được phép thực hiện command làm phát sinh event không?
2. Service đang xử lý event có được phép thực hiện tác vụ của chính nó không?

Câu hỏi thứ nhất được kiểm tra tại command boundary trước khi event được tạo. Câu hỏi thứ hai được kiểm tra bằng service identity và quyền của consumer đối với tài nguyên mà nó sở hữu.

Nếu audit cần biết ai khởi tạo hành động, event có thể mang actorId đã được xác minh, tenantId, thời điểm và correlationId. Consumer dùng thông tin này để ghi audit hoặc áp dụng chính sách nghiệp vụ đã thỏa thuận. Không xem actorId trong payload là credential để consumer mạo danh người dùng.

Ví dụ metadata tối thiểu:

~~~java
public record EventMetadata(
    UUID eventId,
    String actorId,
    String tenantId,
    UUID correlationId,
    Instant occurredAt
) {}
~~~

Các trường có thể được đặt trong envelope hoặc message header tùy hợp đồng. Cần bảo đảm giá trị actor và tenant được lấy từ context đã xác thực, không sao chép mù quáng từ request.

## 10. Phân quyền và externalization trong Spring Modulith

Spring Modulith có thể kết nối application event với externalization qua adapter và cấu hình transport. Việc đánh dấu event để externalize, ví dụ dùng annotation `@Externalized`, chỉ mô tả rằng event được đưa ra ngoài theo cấu hình. Annotation đó không phải authorization policy và không kiểm tra caller có quyền phát event hay không.

Ví dụ minh họa event được externalize:

~~~java
@Externalized("orders")
public record OrderConfirmed(
    UUID eventId,
    UUID orderId,
    String tenantId,
    Instant occurredAt
) {}
~~~

Đích `orders` là tên minh họa; adapter và broker destination phải được cấu hình phù hợp. Quyền caller vẫn phải được kiểm tra ở application service trước khi phát event. Publisher service identity cần được giới hạn quyền ghi tại broker.

Event Publication Registry theo dõi publication đến listener trong ứng dụng và hỗ trợ phục hồi theo cấu hình. Registry không thay thế authorization và cũng không quyết định broker principal nào được publish vào destination nào.

## 11. Kiểm tra quyền ở consumer nhận event

Phân quyền publish không đủ nếu consumer tin mọi message nhận được. Broker ACL giới hạn principal có thể gửi message vào destination, nhưng consumer vẫn nên xác thực cấu trúc, event type, schema và nguồn gửi theo trust model của hệ thống.

Consumer cần:

- Chỉ chấp nhận event type nằm trong allow-list.
- Kiểm tra schema version và payload bắt buộc.
- Xác định tenant từ envelope đã được xác minh và kiểm tra quyền truy cập dữ liệu.
- Không thực thi command đặc quyền chỉ dựa trên trường actorId hoặc role do publisher gửi.
- Áp dụng idempotency và kiểm tra state transition.
- Cách ly message sai schema, sai nguồn hoặc không đáp ứng policy.
- Ghi audit đủ để truy vết mà không log bí mật.

Nếu message đi qua nhiều broker hoặc tổ chức, có thể cần chữ ký message hoặc cơ chế xác minh nguồn gửi ở lớp ứng dụng. Chữ ký chỉ xác thực nguồn và tính toàn vẹn; consumer vẫn phải kiểm tra event có hợp lệ trong ngữ cảnh domain hay không.

## 12. Audit quyết định publish

Với event quan trọng, cần ghi nhận ai yêu cầu hành động, policy nào được áp dụng và kết quả authorization. Audit giúp điều tra khi event được phát sai hoặc một caller thực hiện hành động vượt quyền.

Thông tin audit có thể gồm:

| Trường | Mục đích |
|---|---|
| actorId/servicePrincipal | Danh tính caller đã xác thực |
| tenantId | Phạm vi tenant |
| action | Hành động nghiệp vụ được yêu cầu |
| resourceId | Tài nguyên được thao tác |
| eventType | Event được phát sau khi xử lý thành công |
| authorizationResult | ALLOWED hoặc DENIED |
| policy/version | Phiên bản policy được áp dụng |
| correlationId | Liên kết request và event |
| occurredAt | Thời điểm quyết định |

Không ghi access token, password, private key hoặc toàn bộ payload nhạy cảm vào audit. Với quyết định bị từ chối, ghi đủ thông tin để điều tra nhưng tránh tiết lộ dữ liệu tài nguyên cho caller không có quyền.

Audit event publish và audit truy cập broker có thể nằm ở hai hệ thống khác nhau. Cần liên kết chúng bằng correlationId hoặc eventId để điều tra từ quyết định nghiệp vụ đến message trên broker.

## 13. Thu hồi quyền và thay đổi policy

Quyền publish thay đổi theo vòng đời nhân sự, service và hệ thống. Khi một service ngừng hoạt động hoặc credential bị lộ, cần có khả năng thu hồi quyền mà không phải thay đổi mọi producer khác.

Quy trình quản lý quyền nên gồm:

1. Gán owner cho từng service identity và destination.
2. Cấp quyền tối thiểu theo chức năng thực tế.
3. Ghi nhận lý do, thời hạn và người phê duyệt khi cấp quyền nhạy cảm.
4. Định kỳ rà soát quyền không còn sử dụng.
5. Luân chuyển credential và cập nhật secret an toàn.
6. Thu hồi quyền khi service bị decommission hoặc có sự cố.
7. Kiểm tra producer còn hoạt động đúng sau khi policy thay đổi.

Không nên dùng credential production trong môi trường local hoặc test. Môi trường phát triển cần broker identity và destination riêng để lỗi cấu hình không ảnh hưởng dữ liệu production.

## 14. Kiểm thử phân quyền publish

Kiểm thử cần chứng minh cả trường hợp được phép và bị từ chối. Một test chỉ xác nhận event được phát khi người dùng hợp lệ chưa đủ để chứng minh các đường gọi khác không vượt qua policy.

Các trường hợp nên kiểm tra:

- Người dùng không có authority không thể thực hiện command và không phát event.
- Người dùng có authority nhưng không thuộc tenant sở hữu tài nguyên bị từ chối.
- Người dùng có quyền nhưng domain state không hợp lệ thì event không được phát.
- Caller không thể truyền event type hoặc destination tùy ý.
- Service identity chỉ publish được vào exchange/topic được cấp.
- Publisher không có quyền configure/delete topology nếu không cần.
- Consumer từ chối event type hoặc schema không nằm trong allow-list.
- Event xử lý bất đồng bộ vẫn có actor/tenant metadata đã xác minh mà không phụ thuộc SecurityContext thread-local.
- Credential bị thu hồi không thể tiếp tục publish.
- Message giả mạo actorId hoặc tenantId không vượt qua policy ở consumer.

Có thể dùng test Spring Security với MockMvc hoặc method security test support để kiểm tra quyền caller; integration test với broker thật hoặc container phù hợp để xác minh ACL. Mock publisher chỉ chứng minh application service gọi publisher, không chứng minh broker thực sự từ chối credential thiếu quyền.

## 15. Sơ đồ quyết định publish

~~~mermaid
flowchart TD
    A[Caller gửi command] --> B[Authenticate principal]
    B --> C{Principal hợp lệ?}
    C -- Không --> D[Từ chối request]
    C -- Có --> E[Authorize action và tenant/resource]
    E --> F{Được phép?}
    F -- Không --> G[Ghi audit DENIED]
    F -- Có --> H[Module sở hữu kiểm tra domain invariant]
    H --> I{Command hợp lệ?}
    I -- Không --> J[Trả lỗi nghiệp vụ]
    I -- Có --> K[Commit thay đổi và ghi nhận event]
    K --> L[Publisher dùng service identity]
    L --> M{Broker ACL cho phép?}
    M -- Không --> N[Ghi lỗi giao nhận và cảnh báo]
    M -- Có --> O[Broker nhận message]
    O --> P[Consumer validate event và policy]
~~~

Sơ đồ mô tả các lớp kiểm soát từ caller đến broker và consumer. Việc publish application event nội bộ và việc gửi message ra broker có thể là hai chặng khác nhau; cần đặt authorization ở command boundary và ACL ở transport boundary tương ứng.

## 16. Checklist triển khai

- [ ] Mỗi event có module sở hữu và điều kiện phát rõ ràng.
- [ ] Caller được xác thực trước khi xử lý command.
- [ ] Authorization kiểm tra cả action và quyền trên tài nguyên/tenant.
- [ ] Domain invariant được kiểm tra trước khi phát event.
- [ ] Không nhận event type, class hoặc destination tùy ý từ caller.
- [ ] ApplicationEventPublisher không bị xem nhầm là cơ chế authorization tự động.
- [ ] Publisher dùng service identity riêng và quyền tối thiểu.
- [ ] Broker ACL giới hạn destination và quyền configure/read/write phù hợp.
- [ ] Credential được lưu trong secret manager, có TLS và quy trình rotation.
- [ ] Event chỉ mang actor/tenant metadata đã xác minh, không chứa token hoặc session.
- [ ] Listener bất đồng bộ không phụ thuộc SecurityContext của request ban đầu.
- [ ] Consumer validate event type, schema, nguồn và tenant boundary.
- [ ] Có audit cho quyết định ALLOWED/DENIED và event được phát.
- [ ] Có kiểm thử quyền caller, broker ACL, thu hồi credential và message giả mạo.
- [ ] Có owner và quy trình rà soát/thu hồi quyền định kỳ.

## 17. Nguyên tắc phân quyền publish

Phân quyền publish bắt đầu từ quyền thực hiện command nghiệp vụ và quyền sở hữu sự thật mà event công bố. Caller chỉ được yêu cầu hành động trong phạm vi authority và tài nguyên được phép; module sở hữu kiểm tra domain invariant và phát event sau khi hành động hợp lệ.

Khi event đi ra broker, publisher dùng service identity riêng với ACL tối thiểu trên destination cần thiết. Spring Modulith giúp tổ chức ranh giới module và publication, còn Spring Security và broker ACL đảm nhiệm các lớp authorization tương ứng. Kết hợp audit, tenant isolation, xác thực event ở consumer và kiểm thử cả trường hợp từ chối sẽ giúp ngăn publisher phát sự kiện vượt quyền mà vẫn giữ được luồng giao tiếp bất đồng bộ đáng tin cậy.
