# Chọn event nội bộ

Trong Spring Modulith, application event là một cách để module công bố rằng một sự việc nghiệp vụ đã xảy ra, để các module quan tâm có thể phản ứng mà không cần module phát gọi trực tiếp từng module nhận. Tuy nhiên, không phải mọi lời gọi giữa module đều nên chuyển thành event. Chọn event nội bộ đúng lúc giúp giảm phụ thuộc và bảo vệ ranh giới module; dùng event sai chỗ có thể làm luồng nghiệp vụ khó theo dõi, khó xử lý lỗi và khó xác định kết quả.

**Event nội bộ** phù hợp khi module phát muốn thông báo một sự kiện đã xảy ra và không cần điều khiển chi tiết cách các module khác phản ứng. Nếu bên gọi cần một kết quả ngay, cần yêu cầu một hành động cụ thể hoặc phải phối hợp nhiều bước đồng bộ, service call hoặc command thường là lựa chọn rõ ràng hơn.

## 1. Event nội bộ là gì?

Event nội bộ là thông điệp được phát trong phạm vi một ứng dụng Spring Modulith để thông báo một sự kiện nghiệp vụ. Event thường diễn tả một sự thật đã xảy ra, chẳng hạn:

- Đơn hàng đã được xác nhận.
- Kho đã giữ chỗ cho một mặt hàng.
- Hóa đơn đã được phát hành.
- Tài khoản đã được kích hoạt.
- Yêu cầu hoàn tiền đã được chấp thuận.

Module phát chịu trách nhiệm về sự thật nghiệp vụ và contract của event. Các module nhận đăng ký listener để cập nhật read model, tạo tác vụ tiếp theo hoặc thực hiện phản ứng thuộc trách nhiệm của chúng.

Ví dụ, module Orders xác nhận đơn hàng và phát OrderConfirmed. Module Inventory có thể giữ chỗ hàng, module Notifications có thể chuẩn bị thông báo và module Analytics có thể cập nhật dữ liệu tổng hợp. Orders không cần biết từng module sẽ thực hiện những bước nào.

Event nội bộ vẫn là một contract giữa các module. Việc event chỉ truyền trong một process không có nghĩa module khác được truy cập package nội bộ hoặc phụ thuộc vào implementation của module phát.

## 2. Bắt đầu từ nhu cầu giao tiếp

Trước khi tạo event, hãy mô tả điều mà module đang cần thực hiện:

- Cần lấy dữ liệu để trả kết quả cho request hiện tại?
- Cần yêu cầu một module thực hiện hành động?
- Cần thông báo một sự việc đã hoàn tất để các bên quan tâm tự phản ứng?
- Cần thực hiện nhiều side effect độc lập sau khi giao dịch nghiệp vụ thành công?
- Cần giao tiếp với hệ thống ngoài hoặc lưu thông điệp để xử lý sau?

Câu trả lời quyết định kiểu giao tiếp phù hợp. Đừng bắt đầu bằng việc tìm annotation hoặc chọn cơ chế async. Hãy bắt đầu bằng ý nghĩa nghiệp vụ và yêu cầu về kết quả.

Một quy tắc hữu ích:

- **Yêu cầu hành động:** dùng command hoặc service API.
- **Yêu cầu dữ liệu:** dùng query hoặc service API trả kết quả.
- **Thông báo sự việc đã xảy ra:** cân nhắc event.
- **Giao tiếp ra ngoài ứng dụng:** dùng integration event hoặc adapter externalization có contract riêng.

## 3. Event, command và service call khác nhau thế nào?

| Cơ chế | Ý nghĩa | Bên gửi có mong đợi gì? | Quan hệ phụ thuộc |
|---|---|---|---|
| Service call | Gọi một thao tác hoặc truy vấn cụ thể | Thường cần kết quả hoặc lỗi ngay | Bên gọi biết API của bên được gọi |
| Command | Yêu cầu một hành động có chủ đích | Có một nơi chịu trách nhiệm xử lý command | Có đích xử lý rõ |
| Event | Thông báo một sự việc đã xảy ra | Không điều khiển cách từng subscriber phản ứng | Producer không cần biết danh sách subscriber |

Ví dụ:

- PlaceOrderCommand yêu cầu tạo đơn hàng.
- OrderService.placeOrder() là lời gọi trực tiếp để thực hiện nghiệp vụ tạo đơn.
- OrderPlaced là sự kiện cho biết đơn hàng đã được tạo thành công.

Không đặt tên event như một mệnh lệnh, ví dụ SendEmailNow hoặc ReserveStockNow, nếu ý nghĩa thực tế là yêu cầu một module thực hiện hành động. Những tên này phù hợp với command hơn. Event nên mô tả sự thật ở thì quá khứ hoặc trạng thái đã được xác lập.

Một command thường có một handler có trách nhiệm quyết định kết quả. Một event có thể có không, một hoặc nhiều listener; producer không nên dựa vào một subscriber cụ thể để hoàn thành logic bắt buộc nếu contract không bảo đảm điều đó.

## 4. Khi nào nên chọn event nội bộ?

Event nội bộ thường phù hợp trong các trường hợp sau:

**Nhiều module cần phản ứng với cùng một sự kiện.** Module phát không nên phụ thuộc vào danh sách module nhận. Ví dụ OrderConfirmed có thể được dùng bởi Inventory, Notifications và Analytics.

**Phản ứng có thể tách khỏi giao dịch chính.** Sau khi đơn hàng được commit, các module khác có thể cập nhật projection hoặc khởi tạo công việc riêng. Người dùng không nhất thiết phải chờ mọi phản ứng hoàn tất.

**Module phát không cần kết quả của listener.** Nếu Orders chỉ cần xác nhận đơn hàng đã được lưu, nó không cần biết Notifications đã gửi email hay Analytics đã cập nhật dashboard.

**Muốn công bố một sự thật nghiệp vụ ổn định.** Event có thể trở thành contract giúp các module khác mở rộng mà không sửa code của producer.

**Các phản ứng có vòng đời và khả năng phục hồi riêng.** Listener có thể có retry, quan sát và xử lý lỗi theo trách nhiệm của module nhận.

Event đặc biệt hữu ích khi số lượng subscriber có thể tăng theo thời gian. Thêm một listener mới không cần sửa producer, miễn event contract vẫn phù hợp và ranh giới module được giữ đúng.

## 5. Khi nào không nên dùng event?

Không dùng event chỉ để tránh một lời gọi method. Những trường hợp sau thường nên giữ service call hoặc command:

- Bên gọi cần giá trị trả về để quyết định bước tiếp theo ngay lập tức.
- Bên gọi cần biết thao tác đã thành công hay thất bại trước khi trả response.
- Hai bước phải cùng thành công hoặc cùng rollback trong một transaction.
- Một thao tác có đích xử lý duy nhất và semantics yêu cầu hành động rõ ràng.
- Luồng nghiệp vụ cần thứ tự điều khiển chặt chẽ giữa các bước.
- Event chỉ bọc một lời gọi đồng bộ mà không tạo thêm ranh giới hay khả năng mở rộng.

Ví dụ, nếu Checkout cần hỏi Pricing để tính tổng tiền trước khi xác nhận đơn hàng, gọi Pricing API là rõ ràng hơn phát PriceRequested rồi chờ một event PriceCalculated quay lại trong cùng request. Cách thứ hai tạo một workflow bất đồng bộ phức tạp trong khi nhu cầu thực tế chỉ là truy vấn.

Nếu một module cần bảo đảm Inventory đã giữ chỗ thành công trước khi xác nhận đơn hàng, đừng phát OrderConfirmed rồi giả định listener Inventory sẽ chạy ngay. Hãy thiết kế command/workflow có kết quả rõ, hoặc mô hình hóa quy trình bất đồng bộ bằng trạng thái và compensation nếu nghiệp vụ cho phép.

## 6. Phân biệt event nội bộ và integration event

Event nội bộ phục vụ giao tiếp giữa các module trong cùng ứng dụng. Integration event là contract được công bố cho hệ thống ngoài hoặc consumer độc lập.

| Tiêu chí | Event nội bộ | Integration event |
|---|---|---|
| Phạm vi | Trong ứng dụng Modulith | Qua broker/API tới hệ thống khác |
| Consumer | Module và listener nội bộ | Service, ứng dụng hoặc đối tác ngoài |
| Contract | Có thể gắn với mô hình ứng dụng, nhưng phải ổn định giữa module | Cần versioning và compatibility nghiêm ngặt hơn |
| Vận chuyển | Spring application event | Kafka, message broker hoặc giao thức tích hợp |
| Bảo mật | Theo ranh giới module và quyền truy cập ứng dụng | Cần ACL, authentication, data classification |
| Vòng đời | Thường đi cùng vòng đời release ứng dụng | Producer và consumer có thể deploy độc lập |

Không nên đưa entity nội bộ hoặc object persistence vào integration event. Khi cần externalize một sự kiện, hãy ánh xạ từ event nghiệp vụ nội bộ sang contract bên ngoài có chủ đích. Điều này giúp thay đổi nội bộ không tự động phá vỡ hệ thống đối tác.

Spring Modulith hỗ trợ externalization cho những event được cấu hình tương ứng, ví dụ thông qua metadata như Externalized. Không đánh dấu mọi event nội bộ là externalized. Chỉ công bố ra ngoài khi có nhu cầu tích hợp và đã xác định owner, schema, version, dữ liệu và delivery policy.

## 7. Event nên thuộc module nào?

Module sở hữu sự thật nghiệp vụ nên sở hữu event contract mô tả sự thật đó. Nếu Orders quyết định đơn hàng đã được xác nhận, OrderConfirmed thuộc về contract của Orders. Module khác có thể tiêu thụ event thông qua API được công bố.

Một số nguyên tắc:

- Event được đặt trong package API hoặc named interface mà module sở hữu công bố.
- Listener của module nhận nằm trong module nhận.
- Producer không import implementation listener.
- Consumer không truy cập repository hoặc entity nội bộ của producer.
- Chỉ công bố dữ liệu cần thiết để subscriber hiểu sự kiện.
- Không đặt event dùng chung vào một package common tùy tiện nếu không có module sở hữu contract rõ ràng.

Nếu nhiều module cùng định nghĩa lại một event giống nhau, semantics có thể dần lệch. Hãy có một nguồn contract có owner. Consumer có thể tạo model nội bộ riêng từ event công bố, nhưng không nên sao chép và sửa ý nghĩa event.

## 8. Thiết kế payload event nội bộ

Payload nên chứa đủ dữ liệu để listener thực hiện trách nhiệm của mình mà không cần truy cập trực tiếp vào nội bộ module phát. Tuy nhiên, không nên biến event thành bản sao toàn bộ aggregate.

Ví dụ:

~~~java
public record OrderConfirmed(
    UUID eventId,
    UUID orderId,
    Instant occurredAt,
    long aggregateVersion,
    BigDecimal totalAmount,
    String currency
) {}
~~~

Các trường thường hữu ích:

- Event ID ổn định để deduplicate và điều tra.
- Aggregate ID để xác định đối tượng nghiệp vụ.
- Occurred-at để biết thời điểm sự kiện xảy ra.
- Aggregate version hoặc sequence nếu cần phát hiện event cũ hoặc sai thứ tự.
- Các giá trị nghiệp vụ cần thiết cho subscriber.
- Correlation/causation metadata nếu cần nối workflow.

Tránh đưa JPA entity, lazy proxy, repository, service hoặc object có vòng tham chiếu vào payload. Event nên bất biến, dễ serialize khi cần và không phụ thuộc vào trạng thái persistence context.

Nếu listener cần dữ liệu chi tiết hơn, có thể gọi query API công khai của module sở hữu dữ liệu. Cân nhắc trade-off: event snapshot giảm số lần gọi và giúp consumer xử lý độc lập; event chỉ chứa ID giữ payload nhỏ nhưng listener phải truy vấn nguồn và có thể thấy trạng thái đã thay đổi sau thời điểm event.

## 9. Chọn snapshot event hay event chỉ chứa định danh

Có hai cách thiết kế phổ biến:

| Kiểu payload | Ưu điểm | Đánh đổi |
|---|---|---|
| Snapshot chứa các trường cần thiết tại thời điểm phát | Listener xử lý được theo dữ liệu của sự kiện, ít phụ thuộc query lại | Payload lớn hơn và cần quản lý schema |
| Event chứa ID và metadata tối thiểu | Contract gọn, tránh sao chép nhiều dữ liệu | Listener phải query module nguồn và có thể đọc trạng thái mới hơn |

Chọn snapshot khi ý nghĩa sự kiện gắn với giá trị tại thời điểm xảy ra. Ví dụ OrderPaid nên mang số tiền và currency đã thanh toán nếu listener cần ghi nhận chính xác giao dịch đó.

Chọn ID khi listener cần trạng thái hiện tại hoặc payload lớn không cần thiết. Tuy nhiên, phải cung cấp query API có ranh giới rõ và chấp nhận rằng dữ liệu truy vấn có thể đã thay đổi.

Không dùng một quy tắc duy nhất cho mọi event. Câu hỏi quan trọng là subscriber cần biết điều gì để phản ứng đúng với sự thật đã được công bố.

## 10. Chọn đồng bộ hay bất đồng bộ

Event có thể được xử lý đồng bộ trong thread phát hoặc bất đồng bộ qua executor/listener được cấu hình.

| Cách xử lý | Phù hợp khi | Tác động |
|---|---|---|
| Đồng bộ | Phản ứng ngắn, cần hoàn tất trong cùng luồng gọi và chấp nhận phụ thuộc thời gian | Producer có thể bị ảnh hưởng bởi thời gian và exception của listener |
| Sau commit, bất đồng bộ | Phản ứng không cần nằm trong request và chỉ nên chạy khi transaction nguồn thành công | Có độ trễ, cần theo dõi và phục hồi |
| Externalized qua broker | Consumer độc lập hoặc hệ thống ngoài cần nhận event | Có thêm ranh giới vận chuyển, serialization và vận hành |

Không chọn async chỉ vì muốn tăng tốc. Async làm thay đổi semantics: caller không nhận kết quả trực tiếp, lỗi xảy ra sau khi request kết thúc và dữ liệu có thể được cập nhật trễ. Cần có trạng thái, retry, idempotency và observability tương ứng.

Với Spring Modulith, @ApplicationModuleListener thường được dùng cho listener xử lý sau commit và bất đồng bộ theo semantics của framework. Cần hiểu cấu hình transaction, executor và phiên bản đang dùng. Không giả định mọi @EventListener đều có cùng hành vi.

## 11. Gắn event với transaction nghiệp vụ

Một event như OrderConfirmed chỉ nên được xử lý như sự thật đã xảy ra sau khi transaction xác nhận đơn hàng commit thành công. Nếu transaction rollback nhưng listener đã tạo side effect, hệ thống có thể gửi thông báo hoặc giữ hàng cho một đơn không tồn tại.

Với listener sau commit, quy trình khái quát:

~~~text
Begin transaction
       |
       v
Update order state
       |
       v
Publish OrderConfirmed
       |
       v
Commit transaction
       |
       v
Invoke after-commit listener
       |
       v
Update projection / trigger follow-up
~~~

Nếu transaction rollback, listener after-commit không được thực hiện side effect như thể event đã commit. Kiểm thử cần bao gồm cả nhánh commit và rollback.

Không nhầm việc publish event trong application context với việc lưu event bền vững. Nếu cần bảo đảm phục hồi qua restart hoặc giao event ra broker, phải hiểu cơ chế publication registry, outbox hoặc externalization adapter đang sử dụng.

## 12. Xử lý lỗi và khả năng phục hồi của listener

Khi listener thất bại, cần quyết định lỗi có thể retry, lỗi vĩnh viễn hay lỗi nghiệp vụ có thể bỏ qua. Với listener được Spring Modulith theo dõi bằng Event Publication Registry, publication chưa hoàn tất có thể được nhận diện và phục hồi theo cơ chế phù hợp.

Một số nguyên tắc:

- Không bắt exception rồi chỉ ghi log nếu publication cần được đánh dấu thất bại để retry.
- Listener cần idempotent vì resubmit có thể làm cùng event được xử lý lại.
- Retry có giới hạn, backoff và cảnh báo khi hết ngân sách.
- Lỗi payload hoặc schema không hợp lệ cần quarantine/dead-letter theo policy.
- Nếu thao tác ngoài có kết quả không xác định, reconcile trước khi retry hoặc compensation.
- Ghi audit cho quyết định skip hoặc xử lý bù trừ.

Event Publication Registry theo dõi publication tới listener; nó không tự thay thế event store hoặc toàn bộ retry policy của ứng dụng. Khi event có side effect quan trọng, cần thiết kế persistence và quy trình vận hành rõ.

## 13. Tránh tạo chuỗi event khó kiểm soát

Event giúp giảm phụ thuộc trực tiếp nhưng có thể tạo luồng nghiệp vụ khó hiểu nếu listener phát thêm event mà không có quy tắc.

Ví dụ một chuỗi:

~~~text
OrderConfirmed
      |
      v
InventoryReserved
      |
      v
PaymentRequested
      |
      v
PaymentCaptured
      |
      v
ShipmentCreated
~~~

Chuỗi này có thể hợp lệ nếu mô hình hóa một workflow bất đồng bộ có trạng thái, timeout và compensation. Nhưng nếu mỗi listener phát event tiếp theo mà không có owner điều phối, việc xác định toàn bộ quy trình và xử lý thất bại sẽ khó hơn.

Khi workflow có nhiều bước bắt buộc, điều kiện rẽ nhánh, timeout hoặc compensation, hãy cân nhắc process manager/saga hoặc một application service điều phối. Event có thể thông báo kết quả của từng bước; nó không cần thay thế nơi quản lý trạng thái quy trình.

Đặt tên event theo sự thật đã xảy ra và chỉ phát sau khi module sở hữu sự thật đó xác nhận trạng thái. Tránh phát event mang ý nghĩa dự đoán hoặc ý định như thể hành động đã hoàn tất.

## 14. Giữ ranh giới module bằng contract được công bố

Một consumer chỉ nên phụ thuộc vào event contract mà module phát công bố. Không import class nằm trong package internal, entity hoặc repository của module khác.

Nếu Spring Modulith phát hiện module A phụ thuộc vào type nội bộ của module B, hãy xem đó là tín hiệu cần kiểm tra thiết kế. Có thể module B cần công bố event type qua named interface hoặc consumer cần dùng API khác.

Event nội bộ không có nghĩa mọi module đều được đọc mọi event. Chỉ module có lý do nghiệp vụ mới nên đăng ký listener. Tránh dùng một event tổng quát như EntityChanged rồi để nhiều consumer tự truy vấn và suy đoán điều gì đã thay đổi.

Contract nên có owner, semantics, payload, version và quy tắc thay đổi. Khi thêm trường hoặc đổi ý nghĩa, xem xét consumer hiện tại và dữ liệu publication còn pending.

## 15. Ví dụ phát và nhận event trong Spring Modulith

Module Orders phát event sau khi xác nhận đơn:

~~~java
@Service
class OrderConfirmationService {

    private final ApplicationEventPublisher events;

    OrderConfirmationService(ApplicationEventPublisher events) {
        this.events = events;
    }

    @Transactional
    public void confirm(Order order) {
        order.confirm();

        events.publishEvent(new OrderConfirmed(
            UUID.randomUUID(),
            order.getId(),
            Instant.now(),
            order.getVersion(),
            order.getTotalAmount(),
            order.getCurrency()
        ));
    }
}
~~~

Module Notifications đăng ký listener:

~~~java
@Component
class OrderNotificationListener {

    private final NotificationService notifications;

    OrderNotificationListener(NotificationService notifications) {
        this.notifications = notifications;
    }

    @ApplicationModuleListener
    void on(OrderConfirmed event) {
        notifications.prepareOrderConfirmation(event.orderId());
    }
}
~~~

Ví dụ minh họa. Trong ứng dụng thực tế, event ID nên được tạo theo cơ chế ổn định và có thể lưu cùng transaction/outbox nếu cần deduplication qua restart. Không truyền entity Order vào listener; payload chỉ mang contract cần thiết.

Nếu Notifications cần gửi email ra hệ thống ngoài, listener có thể ghi một notification job/outbox bền vững rồi worker gửi sau. Không nên giữ transaction của listener mở trong lúc gọi dịch vụ email hoặc chờ network.

## 16. Kiểm thử quyết định dùng event

Kiểm thử nên xác minh cả contract và semantics:

1. Module phát event đúng khi sự kiện nghiệp vụ được xác lập.
2. Transaction rollback không kích hoạt listener after-commit.
3. Listener nhận đúng payload và không truy cập package nội bộ của producer.
4. Listener không được gọi nếu event không được phát.
5. Nhiều listener có thể phản ứng độc lập theo contract.
6. Listener failure không bị che giấu nếu publication cần retry.
7. Redelivery không tạo side effect trùng.
8. Consumer không giả định thứ tự toàn cục khi event không có ordering guarantee.
9. Thay đổi payload vẫn tương thích với listener hiện tại.
10. Kiểm tra cấu trúc Spring Modulith không phát hiện dependency vào package nội bộ ngoài ý muốn.

Dùng unit test để kiểm tra logic handler và integration test để xác minh transaction, event publication và listener wiring. Với listener bất đồng bộ, chờ điều kiện cuối cùng bằng timeout hữu hạn; không assertion ngay sau publish nếu công việc chưa hoàn tất.

## 17. Checklist quyết định

Trước khi chọn event nội bộ, trả lời các câu hỏi:

- Đây có phải sự việc nghiệp vụ đã xảy ra hay chỉ là yêu cầu hành động?
- Module phát có cần kết quả đồng bộ từ bên nhận không?
- Có một hay nhiều subscriber có thể quan tâm?
- Các phản ứng có thể tách khỏi transaction chính không?
- Event có được phát sau khi trạng thái nghiệp vụ commit không?
- Module phát có sở hữu và công bố contract rõ ràng không?
- Payload có đủ dữ liệu nhưng không làm lộ implementation nội bộ không?
- Listener có thể xử lý lặp an toàn không?
- Có policy cho lỗi, retry, publication pending và observability không?
- Event chỉ dùng nội bộ hay thực sự cần externalize?
- Nếu workflow có nhiều bước bắt buộc, có cần process manager hoặc saga không?

Nếu câu trả lời cho thấy bên gọi cần điều khiển một hành động và nhận kết quả ngay, hãy dùng service/command. Nếu mục tiêu là công bố sự thật để các module độc lập phản ứng, event nội bộ là lựa chọn phù hợp.

## 18. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách điều chỉnh |
|---|---|---|
| Dùng event thay mọi service call | Luồng điều khiển bị ẩn và khó biết kết quả | Dùng event cho notification, service/command cho request |
| Event mang tên mệnh lệnh | Không rõ sự việc đã xảy ra hay mới được yêu cầu | Đặt tên theo fact nghiệp vụ |
| Producer phụ thuộc listener cụ thể | Mất lợi ích tách rời | Công bố contract và để subscriber tự đăng ký |
| Payload chứa entity hoặc repository | Rò rỉ implementation và khó serialize | Dùng immutable event DTO |
| Listener đọc package internal | Vi phạm module boundary | Dùng event/query API được công bố |
| Async nhưng không có retry/idempotency | Lỗi có thể làm mất phản ứng hoặc lặp side effect | Thiết kế phục hồi và deduplication |
| Phát event trước khi transaction xác lập | Listener có thể phản ứng với dữ liệu rollback | Dùng semantics after-commit phù hợp |
| Dùng event làm workflow engine | Chuỗi phản ứng khó theo dõi và thiếu owner | Dùng process manager/saga khi cần điều phối |
| Externalize mọi event nội bộ | Contract bên ngoài bị gắn với model nội bộ | Tạo integration event riêng khi có nhu cầu |

Chọn event nội bộ là quyết định về ranh giới và semantics giao tiếp, không chỉ là lựa chọn kỹ thuật giữa annotation và method call. Khi event diễn tả đúng một sự thật nghiệp vụ, có owner rõ, payload ổn định và listener được thiết kế để xử lý lỗi cùng redelivery, Spring Modulith có thể mở rộng các phản ứng giữa module mà vẫn giữ được cấu trúc dễ hiểu và có thể vận hành.

