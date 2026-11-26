# Vòng đời bản ghi

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, application events giúp các module Spring Modulith giao tiếp qua sự kiện nghiệp vụ, giảm phụ thuộc trực tiếp và bảo vệ ranh giới module. Publisher công bố sự kiện; listener phản ứng với sự kiện, thường sau khi transaction nghiệp vụ đã commit. **Event Publication Registry** bổ sung khả năng theo dõi việc giao từng sự kiện đến từng transactional listener để ứng dụng biết listener nào đã xử lý xong và listener nào còn cần được khôi phục.

Hiểu đúng vòng đời của một publication record là nền tảng để cấu hình retry, kiểm thử và quan sát giao sự kiện đáng tin cậy. Cần phân biệt sự kiện nghiệp vụ với bản ghi publication: sự kiện mô tả điều đã xảy ra trong nghiệp vụ, còn publication record mô tả việc chuyển sự kiện đó đến một listener cụ thể.

## 1. Sự kiện, listener và publication record

Ví dụ, khi đơn hàng được xác nhận, module Order công bố sự kiện nghiệp vụ **OrderConfirmed**. Module Inventory có thể lắng nghe để giữ hàng; module Notification có thể lắng nghe để gửi thông báo. Publisher chỉ phát ra sự kiện, không cần gọi trực tiếp các service của những module nhận.

Nếu có hai transactional listener phù hợp, registry theo dõi hai lần giao riêng biệt. Một listener có thể hoàn tất trong khi listener còn lại vẫn thất bại. Vì vậy, một sự kiện có thể tương ứng với nhiều publication record và trạng thái của từng record được quản lý độc lập.

| Khái niệm | Ý nghĩa |
| --- | --- |
| Application event | Sự kiện nghiệp vụ được publisher công bố, chẳng hạn **OrderConfirmed**. |
| Listener | Thành phần nhận và xử lý sự kiện, chẳng hạn listener của Inventory. |
| Publication record | Bản ghi theo dõi việc giao một event đến một listener xác định. |
| Incomplete publication | Bản ghi chưa được đánh dấu hoàn tất; có thể cần retry hoặc điều tra. |
| Completed publication | Bản ghi đã được đánh dấu hoàn tất sau khi listener xử lý thành công. |

Registry tập trung vào các transactional event listener mà Spring Modulith theo dõi, chẳng hạn listener dùng **@TransactionalEventListener** hoặc **@ApplicationModuleListener**. Một phương thức chỉ dùng **@EventListener** thông thường không tự động có cùng ngữ nghĩa theo dõi publication. Khi cần khả năng khôi phục, hãy chọn loại listener phù hợp ngay từ đầu.

Một publication record thường mang đủ thông tin để xác định event, listener đích, thời điểm công bố và thời điểm hoàn tất. Cách lưu trữ cụ thể phụ thuộc implementation và phiên bản Spring Modulith; không nên suy luận cấu trúc bảng hay tên cột từ khái niệm ở mức API.

## 2. Các bước trong vòng đời

### Bước 1: Publisher công bố sự kiện

Publisher thường phát sự kiện trong transaction đang cập nhật trạng thái nghiệp vụ. Ví dụ, khi xác nhận đơn hàng, module Order cập nhật đơn hàng rồi công bố **OrderConfirmed**. Việc công bố sự kiện không đồng nghĩa listener đã chạy xong.

### Bước 2: Registry ghi nhận từng đích nhận

Khi event phù hợp với nhiều transactional listener, registry tạo một publication cho mỗi listener. Việc tách theo listener giúp hệ thống xác định chính xác đích nào đã xử lý thành công và đích nào còn dang dở.

Trong luồng có transaction, publication cần được lưu bền vững cùng ranh giới transaction thích hợp. Nếu transaction nghiệp vụ rollback, ứng dụng không được để lại một publication đã commit khiến listener xử lý một thay đổi nghiệp vụ chưa từng được commit. Hãy dùng persistent store được tích hợp với transaction manager của ứng dụng và kiểm thử hành vi rollback trên cấu hình thực tế.

### Bước 3: Listener được gọi sau commit

Với listener ở phase **AFTER_COMMIT**, Spring chỉ gọi handler sau khi transaction phát sự kiện đã commit. Điều này tránh việc module nhận xử lý một sự kiện về thay đổi nghiệp vụ sau đó bị rollback.

**@ApplicationModuleListener** là lựa chọn tiện dụng của Spring Modulith cho giao tiếp giữa các module: annotation này kết hợp listener theo transaction với xử lý bất đồng bộ và transaction riêng cho phần xử lý listener. Nếu dùng **@TransactionalEventListener** trực tiếp, hãy khai báo phase phù hợp, ví dụ **TransactionPhase.AFTER_COMMIT**, và cấu hình transaction cho phần xử lý nếu nghiệp vụ yêu cầu.

### Bước 4: Listener hoàn tất và publication được đánh dấu

Khi handler xử lý thành công, registry đánh dấu publication tương ứng là completed. Từ thời điểm đó, record không còn thuộc nhóm publication đang chờ khôi phục. Nếu một event có nhiều listener, việc hoàn tất của listener A không làm publication của listener B tự động hoàn tất.

Với listener có transaction riêng, cần xem một lần xử lý là thành công khi phần nghiệp vụ của listener đã commit thành công. Nếu handler ném exception hoặc transaction của handler rollback, publication phải tiếp tục được xem là chưa hoàn tất để có thể xử lý lại.

### Bước 5: Lỗi hoặc tiến trình dừng để lại publication chưa hoàn tất

Nếu listener ném exception, máy chủ dừng, hoặc tiến trình bị ngắt trước khi registry ghi nhận completion, publication có thể vẫn ở trạng thái incomplete. Đây là tín hiệu cho cơ chế recovery rằng lần giao đó chưa được xác nhận hoàn tất.

Một publication incomplete không tự chứng minh rằng handler chưa tạo ra bất kỳ tác động nào. Ví dụ, handler có thể gọi dịch vụ thanh toán thành công rồi tiến trình dừng trước khi ghi completion. Khi event được giao lại, tác động bên ngoài có thể bị thực hiện lần thứ hai. Vì vậy, retry phải đi cùng thiết kế idempotent.

## 3. Minh họa luồng publish và xử lý

Ví dụ dưới đây cho thấy publisher phát sự kiện trong transaction và listener của module khác xử lý sau commit. Các import và phần truy cập repository được lược bỏ để tập trung vào vòng đời event.

~~~java
public record OrderConfirmed(UUID orderId, Instant occurredAt) {}
~~~

~~~java
@Service
@RequiredArgsConstructor
class OrderService {

    private final ApplicationEventPublisher events;

    @Transactional
    public void confirm(UUID orderId) {
        // Tải đơn hàng và cập nhật trạng thái trong transaction hiện tại.
        // orderRepository.markConfirmed(orderId);

        events.publishEvent(new OrderConfirmed(orderId, Instant.now()));
    }
}
~~~

~~~java
@Component
@RequiredArgsConstructor
class ReserveInventoryOnOrderConfirmed {

    private final InventoryService inventory;

    @ApplicationModuleListener
    void on(OrderConfirmed event) {
        inventory.reserveFor(event.orderId());
    }
}
~~~

Trong ví dụ, Order không cần biết Inventory triển khai việc giữ hàng ra sao. Khi transaction xác nhận đơn hàng commit, listener mới được thực thi theo cơ chế của **@ApplicationModuleListener**. Registry theo dõi publication đến listener đó và đánh dấu hoàn tất khi lần xử lý thành công.

Luồng khái quát:

~~~mermaid
sequenceDiagram
    participant O as OrderService
    participant E as Spring event dispatch
    participant R as Event Publication Registry
    participant DB as Persistent store
    participant I as Inventory listener

    O->>E: publish OrderConfirmed
    E->>R: Ghi nhận publication cho listener
    R->>DB: Lưu publication chưa hoàn tất
    O->>DB: Commit transaction nghiệp vụ
    E-->>I: Gọi listener sau commit
    I->>I: Xử lý nghiệp vụ Inventory
    alt Xử lý thành công
        I->>R: Xác nhận publication hoàn tất
        R->>DB: Lưu completion
    else Có exception hoặc tiến trình dừng
        Note over R,DB: Publication vẫn incomplete
    end
~~~

Sơ đồ thể hiện ý nghĩa của vòng đời; chi tiết thứ tự gọi nội bộ và cách phối hợp transaction phụ thuộc adapter lưu trữ cùng cấu hình ứng dụng.

## 4. Đọc trạng thái của publication

Ở góc độ vận hành, có thể phân loại record theo các trạng thái sau. **Processing** trong bảng là trạng thái quan sát của handler, không nhất thiết là một giá trị trạng thái được lưu thành cột riêng trong mọi implementation.

| Trạng thái quan sát | Dấu hiệu | Hành động phù hợp |
| --- | --- | --- |
| Incomplete / pending | Chưa có thông tin completion. | Theo dõi tuổi record, xác định listener và nguyên nhân chưa xử lý. |
| Đang xử lý | Listener đang thực thi; record có thể vẫn được xem là incomplete cho đến khi hoàn tất. | Theo dõi thời gian xử lý và lỗi của listener. |
| Completed | Registry đã ghi nhận xử lý thành công. | Đưa record vào chính sách lưu giữ hoặc dọn dẹp đã cấu hình. |
| Incomplete kéo dài | Record vẫn chưa hoàn tất sau ngưỡng vận hành. | Điều tra, sửa nguyên nhân rồi retry có kiểm soát. |

Không nên chỉ đếm tổng số record. Một lượng nhỏ incomplete có tuổi rất cao có thể đáng chú ý hơn nhiều record mới phát sinh trong vài giây. Hãy xem đồng thời số lượng, tuổi của record lâu nhất, listener đích và thời điểm công bố.

## 5. Recovery và retry

Event Publication Registry cho phép ứng dụng tìm các publication chưa hoàn tất và gửi lại theo chính sách recovery. Tùy phiên bản và cấu hình, ứng dụng có thể chọn tự gửi lại publication còn tồn đọng khi khởi động hoặc chủ động điều khiển việc resubmit qua registry. Hãy kiểm tra API và cấu hình của phiên bản Spring Modulith đang dùng trước khi đưa lựa chọn đó vào cấu hình triển khai.

Một quy trình recovery an toàn thường gồm:

1. Truy vấn publication incomplete và xác định listener đích, event cùng thời điểm công bố.
2. Phân biệt lỗi tạm thời với lỗi dữ liệu hoặc lỗi nghiệp vụ không thể tự khắc phục.
3. Khôi phục phụ thuộc bị lỗi, sau đó resubmit publication theo phạm vi đã chọn.
4. Xác nhận record chuyển sang completed và kiểm tra tác động nghiệp vụ chỉ xuất hiện một lần.
5. Cảnh báo hoặc chuyển sang xử lý thủ công nếu publication tiếp tục thất bại sau ngưỡng retry.

Không nên retry liên tục với tốc độ cao khi dependency đang ngừng hoạt động. Ứng dụng nên có giới hạn retry, khoảng chờ tăng dần hoặc cơ chế trì hoãn phù hợp, đồng thời tránh để một listener lỗi làm che khuất tình trạng của các listener khác. Những chính sách như backoff, giới hạn số lần và quy trình xử lý sự kiện lỗi vĩnh viễn cần được thiết kế theo nghiệp vụ; không nên mặc định rằng registry tự cung cấp toàn bộ chính sách đó.

Chỉ xóa hoặc dọn publication completed theo retention policy đã xác định. Không xóa record incomplete chỉ để làm sạch bảng: hành động đó làm mất dấu vết của lần giao chưa được xác nhận và có thể khiến ứng dụng không còn khả năng recovery.

## 6. Vì sao listener phải idempotent

Registry giúp phát hiện và khôi phục publication chưa hoàn tất, nhưng không tạo ra bảo đảm exactly-once cho mọi tác động của listener. Có một khoảng thời gian quan trọng giữa lúc handler tạo tác động và lúc completion được lưu. Nếu tiến trình dừng trong khoảng đó, hệ thống có thể giao lại cùng event.

Thiết kế listener idempotent để xử lý lặp không làm sai trạng thái nghiệp vụ:

- Gắn định danh ổn định cho event và dùng định danh đó làm khóa chống xử lý trùng.
- Với thay đổi trong database, dùng unique constraint hoặc bảng inbox/deduplication được cập nhật trong cùng transaction với thay đổi nghiệp vụ.
- Với API bên ngoài, truyền idempotency key nếu nhà cung cấp hỗ trợ.
- Trước khi tạo tác động, kiểm tra trạng thái nghiệp vụ hiện tại để xác định thao tác đã được áp dụng hay chưa.
- Không dùng thời điểm nhận event làm khóa duy nhất vì cùng một event được retry có thể có thời điểm xử lý khác nhau.

Ví dụ, nếu listener giữ hàng bằng cách tạo một reservation, thao tác nên được ràng buộc với **orderId** hoặc event ID. Khi event được giao lại, listener nhận ra reservation đã tồn tại và kết thúc thành công mà không tạo reservation thứ hai.

Idempotency không thay thế việc xử lý transaction. Các thay đổi database thuộc cùng một nghiệp vụ nên được commit nguyên tử trong transaction của listener. Với tác động bên ngoài database, cần có khóa idempotency hoặc một quy trình đối soát riêng.

## 7. Lưu trữ bền vững và tương thích dữ liệu

Khả năng recovery sau restart phụ thuộc vào nơi lưu publication. Một registry chỉ lưu trong bộ nhớ không thể giữ lại trạng thái chưa hoàn tất sau khi tiến trình mất. Trong môi trường cần giao sự kiện đáng tin cậy, hãy dùng persistent store phù hợp với nền tảng dữ liệu của ứng dụng, chẳng hạn adapter JDBC, JPA hoặc MongoDB do hệ sinh thái Spring Modulith hỗ trợ.

Store cần được cấu hình cùng transaction manager và được kiểm thử trong điều kiện commit, rollback, listener failure và restart. Cũng cần xác định retention cho record completed để cân bằng giữa khả năng điều tra và dung lượng lưu trữ. Record incomplete cần được giữ lại cho đến khi có quyết định recovery hoặc xử lý thủ công rõ ràng.

Publication có thể chứa dữ liệu event đã được serialize. Vì vậy, thay đổi class event, package, tên kiểu hoặc cấu trúc payload có thể ảnh hưởng các record cũ còn tồn đọng. Khi triển khai phiên bản mới, hãy tính đến publication được tạo bởi phiên bản trước: giữ khả năng đọc payload cũ trong khoảng chuyển tiếp, xử lý backlog trước khi xóa kiểu dữ liệu cũ, hoặc cung cấp chiến lược chuyển đổi tương thích. Không nên giả định rằng mọi publication cũ đã biến mất chỉ vì ứng dụng vừa được deploy.

## 8. Kiểm thử vòng đời publication

Unit test cho handler hữu ích để kiểm tra logic nghiệp vụ, nhưng chưa đủ để xác minh registry và transaction phối hợp đúng. Nên có integration test dùng cấu hình persistence tương tự môi trường chạy thật.

Các trường hợp nên kiểm tra:

| Trường hợp | Điều cần xác minh |
| --- | --- |
| Transaction commit | Listener sau commit được gọi và publication tương ứng được đánh dấu completed. |
| Transaction rollback | Listener **AFTER_COMMIT** không xử lý một thay đổi đã rollback; trạng thái publication không bị để lại sai lệch. |
| Nhiều listener | Mỗi listener có trạng thái publication độc lập; một listener thành công không che lỗi của listener khác. |
| Listener ném exception | Publication chưa được xác nhận completed và có thể được tìm thấy trong nhóm incomplete. |
| Resubmit | Sau khi khắc phục lỗi và gửi lại, listener hoàn tất; tác động nghiệp vụ không bị nhân đôi. |
| Restart | Publication incomplete vẫn còn sau khi ứng dụng khởi động lại với persistent store. |

Trong test retry, nên cố ý mô phỏng trường hợp handler đã tạo một phần tác động rồi thất bại. Trường hợp này giúp phát hiện listener chưa idempotent, vốn dễ bị bỏ sót nếu test chỉ ném exception ngay dòng đầu tiên.

## 9. Quan sát trong môi trường chạy thật

Registry cung cấp dữ liệu để xây dựng quan sát theo listener và theo event. Các chỉ số hữu ích gồm số publication incomplete, tuổi của publication lâu nhất, thời gian từ publication đến completion, số lần retry, tỷ lệ listener lỗi và số publication được resubmit. Có thể đặt cảnh báo khi backlog tăng liên tục hoặc khi một publication vượt ngưỡng tuổi theo yêu cầu nghiệp vụ.

Log của publisher và listener nên có event ID, listener ID, correlation ID và business key phù hợp. Nhờ đó, người vận hành có thể lần theo một event từ transaction phát sinh đến từng đích nhận. Tránh ghi toàn bộ payload hoặc dữ liệu nhạy cảm vào log; chỉ ghi các định danh cần thiết để tra cứu.

Khi điều tra một publication incomplete, hãy kiểm tra theo thứ tự: event và listener nào liên quan; record được tạo lúc nào; transaction gốc đã commit chưa; listener có được gọi không; lỗi xảy ra ở bước nào; tác động nghiệp vụ có thể đã được thực hiện một phần chưa; và lần retry tiếp theo có an toàn không. Cách điều tra này giúp tránh resubmit mù quáng đối với listener có side effect bên ngoài.

## 10. Checklist thiết kế

- Publisher công bố event sau khi đã xác định thay đổi nghiệp vụ thuộc transaction nào.
- Listener cần theo dõi dùng transactional listener phù hợp, thường là **@ApplicationModuleListener** hoặc **@TransactionalEventListener**.
- Publication registry dùng persistent store và transaction manager tương thích với yêu cầu durability.
- Thành công chỉ được xác nhận sau khi phần xử lý listener hoàn tất theo transaction của nó.
- Listener idempotent để chịu được việc giao lại sau lỗi hoặc crash.
- Recovery có giới hạn, có quan sát backlog và có cách xử lý lỗi không thể tự khắc phục.
- Record completed có retention policy; record incomplete không bị xóa tùy tiện.
- Integration test bao phủ commit, rollback, nhiều listener, lỗi, retry và restart.
- Event payload có chiến lược tương thích khi ứng dụng nâng cấp trong lúc còn publication tồn đọng.

Vòng đời publication record tạo ra một dấu vết rõ ràng cho việc giao application event giữa các module: record được tạo cho từng listener, được xác nhận khi xử lý thành công và được giữ lại khi cần recovery. Kết hợp registry bền vững, listener idempotent, retry có kiểm soát, kiểm thử transaction và quan sát backlog sẽ giúp giao tiếp qua application events đáng tin cậy hơn mà vẫn giữ các module ít phụ thuộc vào nhau.
