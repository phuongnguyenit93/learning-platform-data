# Retry event

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, application events giúp các module Spring Modulith giao tiếp qua sự kiện nghiệp vụ, giảm phụ thuộc trực tiếp và giữ ranh giới module rõ ràng. Khi một listener gặp lỗi, ứng dụng cần một cách thử xử lý lại mà không làm mất sự kiện và không tạo ra tác dụng phụ lặp ngoài ý muốn. Đây là vai trò của retry event.

Bài này tập trung vào vòng đời một lần giao sự kiện đến listener, cách Spring Modulith ghi nhận publication chưa hoàn tất, cách kích hoạt retry và các điều kiện để retry an toàn. Retry xử lý lỗi kỹ thuật có thể phục hồi; compensation xử lý trạng thái nghiệp vụ cần được đảo hoặc điều chỉnh khi không thể tiếp tục quy trình ban đầu.

## 1. Vì sao listener cần retry?

Giả sử module Order lưu đơn hàng và phát sự kiện OrderPlaced. Module Inventory nhận sự kiện để giữ hàng. Giao dịch tạo đơn hàng có thể đã commit thành công, nhưng listener giữ hàng lại gặp timeout khi gọi dịch vụ kho. Nếu chỉ dựa vào lời gọi listener trong bộ nhớ, tiến trình có thể dừng trước khi xử lý xong và ứng dụng không còn cách biết sự kiện nào chưa được giao thành công.

Các lỗi thường gặp gồm:

- Dịch vụ phụ thuộc tạm thời không khả dụng hoặc trả về lỗi mạng.
- Cơ sở dữ liệu, message broker hay API bên ngoài bị timeout.
- Giới hạn tốc độ khiến lời gọi bị từ chối tạm thời.
- Ứng dụng khởi động lại đúng lúc listener đang xử lý.
- Listener đã thực hiện một phần công việc rồi mới phát sinh lỗi.

Không phải lỗi nào cũng nên retry. Timeout, lỗi kết nối và HTTP 503 thường có thể phục hồi. Dữ liệu không hợp lệ, vi phạm quy tắc nghiệp vụ hoặc yêu cầu bị từ chối vĩnh viễn cần được sửa dữ liệu, xử lý thủ công hoặc bù trừ. Retry vô hạn một lỗi không thể phục hồi chỉ làm tăng tải và che khuất nguyên nhân.

## 2. Vòng đời publication trong Spring Modulith

Spring Modulith cung cấp Event Publication Registry để theo dõi việc giao một event đến từng transactional listener. Registry lưu một publication cho mỗi listener cần nhận event. Khi listener xử lý thành công, publication được đánh dấu hoàn tất. Nếu listener thất bại, publication vẫn ở trạng thái chưa hoàn tất để ứng dụng có thể kiểm tra và gửi lại.

Với listener dùng **@ApplicationModuleListener**, luồng xử lý thông thường có các đặc điểm:

- Listener được gọi sau khi giao dịch phát event commit.
- Việc xử lý listener diễn ra bất đồng bộ.
- Listener chạy trong một giao dịch riêng, độc lập với giao dịch đã phát event.

Nhờ vậy, lỗi ở module nhận không làm rollback giao dịch nghiệp vụ đã commit ở module phát. Registry cũng có thể ghi nhận publication chưa hoàn tất để khôi phục sau đó.

~~~mermaid
flowchart TD
    A["OrderService lưu đơn hàng"] --> B["Phát OrderPlaced trong transaction"]
    B --> C["Registry ghi publication cho listener"]
    C --> D{"Transaction commit?"}
    D -->|Không| E["Rollback: publication cùng transaction bị rollback"]
    D -->|Có| F["Listener bắt đầu xử lý sau commit"]
    F --> G{"Listener thành công?"}
    G -->|Có| H["Đánh dấu publication completed"]
    G -->|Không| I["Publication còn incomplete"]
    I --> J["Retry theo chính sách ứng dụng"]
    J --> F
~~~

Registry chỉ phát huy tác dụng bền vững khi ứng dụng dùng implementation lưu publication vào cơ sở dữ liệu phù hợp, chẳng hạn adapter JDBC hoặc JPA của Spring Modulith. Cần cấu hình dependency, schema và transaction manager tương ứng với cách ứng dụng đang lưu dữ liệu. Nếu chỉ dùng cơ chế lưu trong bộ nhớ, trạng thái theo dõi có thể mất khi tiến trình dừng; cách đó không đáp ứng yêu cầu phục hồi qua lần khởi động lại.

## 3. Phát event và xử lý bằng module listener

Event nên mô tả một sự kiện nghiệp vụ đã xảy ra, mang dữ liệu đủ để listener xử lý mà không phải truy cập trực tiếp repository nội bộ của module phát. Nên có một mã định danh ổn định để hỗ trợ chống xử lý trùng.

~~~java
public record OrderPlaced(
    UUID eventId,
    UUID orderId,
    Instant occurredAt
) {}
~~~

Module Order phát event trong cùng transaction với thao tác lưu đơn hàng:

~~~java
@Service
class OrderService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;
    private final Clock clock;

    OrderService(
            OrderRepository orders,
            ApplicationEventPublisher events,
            Clock clock) {
        this.orders = orders;
        this.events = events;
        this.clock = clock;
    }

    @Transactional
    public void placeOrder(CreateOrder command) {
        Order order = orders.save(Order.from(command));

        events.publishEvent(new OrderPlaced(
            UUID.randomUUID(),
            order.getId(),
            clock.instant()
        ));
    }
}
~~~

Module Inventory đăng ký listener để giữ hàng:

~~~java
@Component
class ReserveInventoryOnOrderPlaced {

    private final InventoryService inventory;

    ReserveInventoryOnOrderPlaced(InventoryService inventory) {
        this.inventory = inventory;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        inventory.reserve(event.orderId(), event.eventId());
    }
}
~~~

Lời gọi **publishEvent** không có nghĩa listener đã hoàn thành ngay tại thời điểm đó. Module phát chỉ công bố sự kiện trong transaction của nó. Registry theo dõi publication, còn listener xử lý sau commit theo cấu hình của annotation. Vì vậy, module Order không cần gọi trực tiếp InventoryService và không cần biết chi tiết giữ hàng được triển khai ra sao.

Event là hợp đồng giữa các module. Khi thay đổi cấu trúc event, cần cân nhắc các listener đang tiêu thụ hợp đồng đó. Tránh đưa entity JPA, repository hoặc đối tượng nội bộ có vòng đời phụ thuộc persistence vào payload. Một event nhỏ, bất biến và có phiên bản rõ ràng sẽ dễ lưu trữ, phát lại và tương thích hơn.

## 4. Kích hoạt retry từ publication chưa hoàn tất

Có thể dùng **IncompleteEventPublications** để yêu cầu Spring Modulith gửi lại các publication chưa hoàn tất. Ví dụ sau cung cấp một thao tác retry các publication cũ hơn một khoảng thời gian:

~~~java
@Component
class EventPublicationRetry {

    private final IncompleteEventPublications publications;

    EventPublicationRetry(IncompleteEventPublications publications) {
        this.publications = publications;
    }

    public void retryStalePublications() {
        publications.resubmitIncompletePublicationsOlderThan(
            Duration.ofMinutes(5)
        );
    }
}
~~~

Ứng dụng có thể gọi thao tác này từ một tác vụ vận hành, một job được lập lịch hoặc một luồng quản trị có phân quyền. Ngưỡng thời gian giúp tránh gửi lại publication vừa được tạo hoặc listener có thể vẫn đang xử lý. Nếu chỉ muốn gửi lại một nhóm event cụ thể, API cũng hỗ trợ lọc publication:

~~~java
public void retryOrderPlacedPublications() {
    publications.resubmitIncompletePublications(
        publication -> publication.getEvent() instanceof OrderPlaced
    );
}
~~~

Bộ lọc theo kiểu event là ví dụ đơn giản. Trong ứng dụng thực tế, cần cân nhắc cả listener đích, thời điểm phát, trạng thái quy trình và nguyên nhân lỗi nếu những thông tin đó được quản lý ở tầng ứng dụng. Chỉ gọi retry cho publication đã đủ điều kiện theo chính sách.

Event Publication Registry theo dõi publication đã hoàn tất hay còn dang dở. Ứng dụng vẫn cần thiết kế chính sách retry phù hợp: khoảng chờ, số lần thử tối đa, backoff, jitter, ngắt retry khi dịch vụ phụ thuộc đang lỗi diện rộng và cách đưa trường hợp vượt giới hạn sang xử lý thủ công. Không nên chạy một job gửi lại liên tục mà không có giới hạn, vì listener lỗi cố định có thể bị gọi dồn dập.

Một chính sách cơ bản có thể phân loại như sau:

| Loại lỗi | Hướng xử lý |
|---|---|
| Timeout, mất kết nối, HTTP 503 | Retry có backoff và jitter |
| HTTP 429 hoặc bị giới hạn tốc độ | Tôn trọng thời gian chờ từ dịch vụ, sau đó retry |
| Dữ liệu thiếu hoặc sai định dạng | Dừng retry tự động, chuyển sang sửa dữ liệu |
| Vi phạm quy tắc nghiệp vụ | Ghi nhận kết quả nghiệp vụ; cân nhắc compensation |
| Vượt số lần retry | Đưa vào hàng chờ xử lý thủ công hoặc quy trình bù trừ |

Backoff tăng dần giúp giảm tải khi dịch vụ phụ thuộc đang phục hồi. Jitter phân tán thời điểm retry của nhiều event, tránh việc tất cả listener cùng gọi lại một dịch vụ tại một thời điểm. Số lần retry và thời gian chờ phải phù hợp với mức độ quan trọng, thời hạn nghiệp vụ và khả năng chịu tải của hệ thống.

## 5. Làm listener idempotent để retry an toàn

Một tình huống quan trọng là listener đã thực hiện tác dụng phụ thành công nhưng tiến trình dừng trước khi registry kịp ghi nhận publication hoàn tất. Khi phục hồi, cùng event có thể được giao lại. Do đó, không thể giả định một listener chỉ chạy đúng một lần.

Listener cần idempotent: nhận cùng một event nhiều lần vẫn đưa hệ thống về cùng một trạng thái nghiệp vụ như xử lý một lần. Có thể thực hiện theo các cách sau:

1. Gắn eventId duy nhất vào payload và dùng nó làm khóa chống trùng.
2. Với thay đổi dữ liệu nội bộ, ghi dấu event đã xử lý và cập nhật dữ liệu nghiệp vụ trong cùng một transaction.
3. Đặt unique constraint cho eventId trong bảng inbox hoặc bảng theo dõi xử lý.
4. Với API bên ngoài, truyền eventId làm idempotency key nếu nhà cung cấp hỗ trợ.
5. Nếu dịch vụ bên ngoài không hỗ trợ idempotency key, lưu trạng thái từng bước và đối soát kết quả trước khi gửi lại.

Ví dụ, một bảng inbox có thể lưu eventId đã được xử lý:

~~~sql
CREATE TABLE processed_event (
    event_id UUID PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Khi nhận event, listener cố ghi eventId vào bảng này trong cùng transaction với thay đổi nghiệp vụ. Nếu khóa đã tồn tại, listener biết event đã được xử lý và có thể kết thúc an toàn. Nếu transaction thất bại, cả dấu xử lý và thay đổi nghiệp vụ cùng rollback. Cú pháp xử lý xung đột cụ thể phụ thuộc hệ quản trị cơ sở dữ liệu.

Với lời gọi ra ngoài transaction cơ sở dữ liệu, idempotency key là đặc biệt quan trọng. Ví dụ, nếu cổng thanh toán đã nhận yêu cầu hoàn tiền nhưng kết nối bị ngắt trước khi ứng dụng nhận phản hồi, retry bằng một yêu cầu mới có thể tạo hai lần hoàn tiền. Dùng cùng khóa idempotency cho mọi lần thử của cùng một nghiệp vụ giúp nhà cung cấp nhận diện đó là cùng một yêu cầu.

Không nên coi Event Publication Registry là cam kết exactly-once cho mọi tác dụng phụ. Registry giúp lưu trạng thái và khôi phục publication; việc chống tác dụng phụ trùng vẫn thuộc trách nhiệm của listener và hệ thống được gọi.

## 6. Compensation khi retry không thể tiếp tục

Retry và compensation giải quyết hai vấn đề khác nhau:

- Retry thử thực hiện lại cùng một bước khi nguyên nhân lỗi có khả năng biến mất.
- Compensation thực hiện một hành động nghiệp vụ mới để đưa quy trình về trạng thái chấp nhận được khi bước ban đầu không thể hoàn thành.

Ví dụ: đơn hàng đã được thanh toán nhưng không thể giữ hàng sau số lần retry cho phép. Ứng dụng có thể chuyển đơn sang trạng thái cần xử lý, yêu cầu hoàn tiền và phát event OrderCompensationRequested. Việc hoàn tiền là một thao tác nghiệp vụ độc lập, có thể cần retry riêng và cũng phải idempotent.

Một quy trình bù trừ nên có các thuộc tính:

- Có trạng thái rõ ràng, chẳng hạn PENDING, IN_PROGRESS, COMPLETED và FAILED.
- Có mã định danh riêng hoặc khóa idempotency để tránh bù trừ hai lần.
- Ghi nhận lý do, thời điểm, event gốc và bước đã hoàn thành.
- Có chính sách retry riêng cho hành động bù trừ.
- Có cơ chế đưa trường hợp không thể tự động giải quyết sang người vận hành.

Không nên xóa publication chưa hoàn tất chỉ để làm sạch danh sách lỗi khi chưa hiểu trạng thái nghiệp vụ. Xóa dấu vết có thể khiến ứng dụng mất khả năng phát lại hoặc đối soát. Chỉ dọn dữ liệu theo chính sách lưu trữ đã xác định và sau khi trạng thái nghiệp vụ được giải quyết.

## 7. Quan sát và vận hành retry

Một cơ chế retry chỉ hữu ích khi đội vận hành biết nó đang hoạt động ra sao. Nên theo dõi tối thiểu:

- Số publication chưa hoàn tất, phân nhóm theo listener và loại event.
- Tuổi của publication chưa hoàn tất lâu nhất.
- Số lần retry, tỷ lệ retry thành công và tỷ lệ thất bại kéo dài.
- Thời gian xử lý listener và thời gian từ lúc phát event đến lúc hoàn tất.
- Số quy trình đang chờ compensation hoặc xử lý thủ công.

Log có cấu trúc nên mang theo eventId, orderId hoặc aggregateId, tên listener, loại event và mã lỗi. Không ghi toàn bộ payload nhạy cảm vào log. Khi cảnh báo, cần đưa ra thông tin đủ để truy vấn publication và xác định module nhận đang gặp vấn đề.

Một màn hình hoặc thao tác quản trị retry nên cho phép người vận hành xem event, listener đích, thời điểm phát, trạng thái và lỗi gần nhất; chọn retry có chủ đích; đồng thời lưu lại người thực hiện và kết quả. Quyền retry hoặc xóa publication cần được giới hạn vì thao tác này có thể kích hoạt lại tác dụng phụ nghiệp vụ.

Cũng cần đặt thời hạn lưu trữ cho publication đã hoàn tất để dữ liệu registry không tăng vô hạn. Việc dọn dẹp phải giữ đủ thời gian phục vụ điều tra và đối soát. Publication chưa hoàn tất cần được xử lý theo quy trình riêng, không áp dụng máy móc cùng chính sách với publication đã hoàn tất.

## 8. Kiểm thử luồng retry

Nên kiểm thử với cấu hình registry và cơ sở dữ liệu gần với môi trường triển khai. Một listener giả lập chỉ ném exception trong unit test có thể chứng minh nhánh xử lý lỗi, nhưng chưa xác nhận được publication có được lưu bền vững và phục hồi sau khi ứng dụng khởi động lại hay không.

Các kịch bản tích hợp nên bao gồm:

1. **Transaction phát event rollback:** đơn hàng không được commit và không để lại publication đã commit.
2. **Listener thất bại:** giao dịch tạo đơn hàng vẫn commit; publication tương ứng còn incomplete.
3. **Retry thành công:** sau khi nguyên nhân lỗi được loại bỏ, gửi lại publication và xác nhận listener hoàn tất.
4. **Khởi động lại ứng dụng:** publication chưa hoàn tất vẫn còn trong kho lưu trữ bền vững và có thể được gửi lại.
5. **Giao event trùng:** gửi cùng eventId nhiều lần nhưng tác dụng phụ nghiệp vụ chỉ được áp dụng một lần.
6. **Retry vượt giới hạn:** quy trình chuyển sang trạng thái chờ xử lý hoặc compensation theo chính sách.
7. **Compensation thất bại:** lỗi của bước bù trừ được theo dõi và phục hồi độc lập.

Khi kiểm thử retry, hãy xác nhận cả ba kết quả: trạng thái nghiệp vụ, trạng thái publication và số lần tác dụng phụ thực sự xảy ra. Không chỉ kiểm tra rằng phương thức listener đã được gọi.

## 9. Quy trình áp dụng

Khi triển khai retry event cho một luồng nghiệp vụ, có thể đi theo trình tự sau:

1. Xác định event và listener nào cần khả năng phục hồi; giữ event payload bất biến và có eventId ổn định.
2. Bảo đảm publication registry dùng kho lưu trữ bền vững và tham gia đúng transaction.
3. Dùng listener phù hợp, thường là **@ApplicationModuleListener** cho xử lý sau commit, bất đồng bộ và trong transaction riêng.
4. Làm listener idempotent trước khi bật retry tự động.
5. Xác định loại lỗi có thể retry, backoff, jitter, giới hạn lần thử và thời hạn xử lý.
6. Xây dựng nhánh compensation cho trường hợp nghiệp vụ không thể tiếp tục.
7. Bổ sung log, metrics, cảnh báo và thao tác vận hành có phân quyền.
8. Kiểm thử rollback, listener failure, retry, restart, duplicate delivery và compensation.

Retry event trong Spring Modulith kết hợp khả năng theo dõi publication với chính sách phục hồi do ứng dụng xác định. Khi registry được lưu bền vững, listener idempotent và quy trình compensation được quản lý rõ ràng, các module có thể giao tiếp qua application events mà vẫn kiểm soát được lỗi phát sinh sau khi giao dịch nghiệp vụ đã commit.

