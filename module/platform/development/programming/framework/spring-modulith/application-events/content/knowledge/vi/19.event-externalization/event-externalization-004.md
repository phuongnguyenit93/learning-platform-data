# Chọn event được externalize

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, application events giúp các module giao tiếp mà không cần phụ thuộc trực tiếp vào nhau. Khi một sự kiện được externalize, nó vượt qua ranh giới ứng dụng để một hệ thống hoặc dịch vụ bên ngoài có thể nhận và phản ứng. Quyết định externalize event nào vì vậy xác định phần nào của mô hình nghiệp vụ trở thành hợp đồng tích hợp mà hệ thống khác có thể dựa vào.

Không phải mọi application event đều nên được gửi ra ngoài. Hãy externalize những sự kiện biểu đạt một sự thật nghiệp vụ có ý nghĩa với một consumer bên ngoài, có hợp đồng dữ liệu đủ ổn định và có thể được xử lý bất đồng bộ. Các sự kiện chỉ phục vụ phối hợp nội bộ, chứa dữ liệu nhạy cảm không cần thiết hoặc không có consumer cụ thể nên ở lại trong ứng dụng.

## 1. Hiểu đúng event được externalize

Application event là thông báo trong phạm vi ứng dụng. Một module có thể phát event để module khác phản ứng mà không cần publisher biết listener nào sẽ nhận. Khi externalize, ứng dụng chuyển một event đã chọn thành thông điệp đi qua ranh giới tiến trình hoặc ranh giới tổ chức, thường thông qua message broker hay một adapter tích hợp.

Cần phân biệt ba loại thông tin:

| Loại | Mục đích | Phạm vi sử dụng |
|---|---|---|
| Domain event | Ghi nhận một điều có ý nghĩa đã xảy ra trong domain | Mô hình nghiệp vụ của module hoặc bounded context sở hữu nó |
| Application event nội bộ | Điều phối công việc giữa các thành phần hoặc module trong cùng ứng dụng | Ranh giới ứng dụng hiện tại |
| Integration event | Công bố một sự thật nghiệp vụ dưới dạng hợp đồng cho consumer bên ngoài | Dịch vụ, ứng dụng hoặc đối tác tích hợp |

Một domain event có thể là nguồn để tạo integration event, nhưng hai khái niệm không nhất thiết phải là cùng một class. Mô hình nội bộ thường chứa kiểu dữ liệu, tên thuộc tính và quy tắc chỉ có ý nghĩa với module sở hữu domain. Integration event cần được thiết kế cho consumer độc lập, có ngữ nghĩa rõ và có vòng đời tương thích riêng.

Ví dụ, module Đơn hàng có thể phát event nội bộ khi trạng thái đơn thay đổi. Hệ thống kho và hệ thống hóa đơn chỉ cần biết rằng đơn hàng đã được xác nhận. Integration event có thể công bố sự thật **OrderConfirmed** với mã đơn, thời điểm xác nhận và những thuộc tính mà các consumer đó thực sự cần.

Externalize một event có nghĩa là chấp nhận duy trì hợp đồng với các consumer. Khi tên event, cấu trúc payload hoặc ngữ nghĩa thay đổi, các consumer có thể bị ảnh hưởng dù chúng không nằm trong cùng repository.

## 2. Bắt đầu từ consumer và nhu cầu nghiệp vụ

Trước khi đánh dấu một event để externalize, hãy xác định ai sẽ nhận nó và họ cần làm gì sau khi nhận. Không nên bắt đầu bằng câu hỏi “event nào có thể gửi lên broker?”; hãy bắt đầu bằng “hệ thống nào cần biết sự thật nghiệp vụ nào?”.

Với mỗi consumer dự kiến, cần trả lời:

- Consumer thuộc module, dịch vụ, ứng dụng hay đối tác nào?
- Consumer cần phản ứng với sự thật nghiệp vụ nào?
- Tác vụ của consumer có thể thực hiện bất đồng bộ không?
- Consumer cần dữ liệu gì để xử lý mà không truy cập trực tiếp database nội bộ?
- Nếu nhận lại cùng một event, consumer có thể nhận biết và xử lý an toàn không?
- Consumer cần biết event theo thứ tự nào, hoặc có thể xử lý độc lập?
- Ai sở hữu hợp đồng và thông báo thay đổi cho các consumer?

Một event có nhiều consumer độc lập thường có giá trị externalization rõ ràng. Tuy nhiên, số lượng consumer không phải tiêu chí duy nhất. Một consumer duy nhất vẫn có thể cần integration event nếu nó nằm ngoài ranh giới triển khai hoặc quyền sở hữu của module phát.

Ví dụ:

| Sự kiện nghiệp vụ | Consumer bên ngoài | Quyết định ban đầu |
|---|---|---|
| Đơn hàng được xác nhận | Kho, hóa đơn, phân tích kinh doanh | Thường nên externalize |
| Hóa đơn được phát hành | Kế toán, cổng hóa đơn điện tử | Thường nên externalize |
| Địa chỉ giao hàng được chuẩn hóa | Chưa có consumer nào cần | Giữ nội bộ cho đến khi có nhu cầu |
| Bộ nhớ đệm trong ứng dụng được làm mới | Chỉ các thành phần trong cùng ứng dụng | Không cần externalize |
| Điểm đánh giá rủi ro nội bộ được tính lại | Chỉ module rủi ro sử dụng | Giữ nội bộ |
| Thanh toán cần được yêu cầu thực hiện | Cổng thanh toán nhận một chỉ thị | Đây thường là command/message yêu cầu hành động, không phải integration event mô tả sự thật đã xảy ra |

Consumer cụ thể giúp xác định phạm vi payload và tránh công bố dữ liệu chỉ vì dữ liệu đó đang có sẵn trong event nội bộ.

## 3. Tiêu chí chọn event

### 3.1. Event biểu đạt một sự thật nghiệp vụ đã xảy ra

Integration event nên mô tả điều đã xảy ra, thường dùng cách diễn đạt ở thì quá khứ: đơn hàng đã được xác nhận, khoản thanh toán đã được ghi nhận, hóa đơn đã được phát hành.

Sự kiện nên có ngữ nghĩa độc lập với cách triển khai nội bộ. Consumer cần hiểu được điều event tuyên bố mà không phải đọc source code của publisher.

Ưu tiên:

- **OrderConfirmed**: đơn hàng đã vượt qua bước xác nhận.
- **PaymentCaptured**: khoản thanh toán đã được thu.
- **InvoiceIssued**: hóa đơn đã được phát hành.

Cân nhắc kỹ những tên chung chung như **EntityUpdated**, **StatusChanged** hoặc **ProcessFinished**. Consumer sẽ khó hiểu thay đổi nào có ý nghĩa, trạng thái trước và sau là gì, và liệu event có đại diện cho một cam kết nghiệp vụ hay chỉ là một thay đổi kỹ thuật.

### 3.2. Consumer có thể hành động từ hợp đồng được công bố

Một event tốt cung cấp đủ ngữ cảnh để consumer quyết định bước tiếp theo. Payload không nhất thiết phải chứa toàn bộ entity. Nó chỉ cần có các trường mà consumer cần để xử lý hoặc tra cứu phần dữ liệu được phép truy cập.

Ví dụ, hệ thống kho có thể cần mã đơn, các dòng hàng, số lượng và địa chỉ giao hàng đã được xác nhận. Hệ thống phân tích có thể chỉ cần mã đơn, tổng tiền, loại tiền và thời điểm. Không nên buộc cả hai consumer nhận một payload lớn chỉ vì publisher có sẵn một object đầy đủ.

Nếu consumer cần truy vấn ngược vào database nội bộ để hiểu event, hợp đồng đang phụ thuộc quá chặt vào implementation. Hãy cung cấp định danh ổn định và một giao diện truy vấn được kiểm soát nếu consumer thực sự cần thêm dữ liệu.

### 3.3. Sự kiện có vòng đời và ngữ nghĩa đủ ổn định

Một integration event có thể được lưu trong broker, retry hoặc replay sau khi publisher đã triển khai phiên bản mới. Vì vậy, payload cần tương thích trong khoảng thời gian event còn có thể được xử lý.

Nên externalize sự thật nghiệp vụ có ý nghĩa lâu dài. Tránh đưa ra ngoài các trạng thái trung gian thay đổi liên tục, tên class nội bộ, tên bảng, trạng thái ORM hoặc chi tiết thuật toán có thể đổi mà không làm thay đổi ý nghĩa nghiệp vụ.

Hãy xác định rõ:

- Khi nào sự kiện được xem là đã xảy ra.
- Module nào có quyền phát biểu sự thật đó.
- Event đại diện cho một lần chuyển trạng thái hay một snapshot.
- Các trường bắt buộc và ý nghĩa của giá trị thiếu.
- Khoảng thời gian consumer cần hỗ trợ schema cũ.
- Cách thông báo và triển khai thay đổi hợp đồng.

### 3.4. Tác vụ phù hợp với giao tiếp bất đồng bộ

Externalization phù hợp khi consumer có thể xử lý sau, không cần publisher chờ kết quả ngay trong cùng request. Nếu nghiệp vụ cần câu trả lời tức thời để quyết định có tiếp tục hay không, hãy xem xét API đồng bộ hoặc một command/query phù hợp.

Không dùng event để che giấu một lời gọi đồng bộ bắt buộc. Khi publisher cần biết ngay consumer có chấp nhận yêu cầu hay không, việc gửi event rồi chờ một phản hồi gián tiếp có thể làm luồng nghiệp vụ khó hiểu và khó vận hành.

### 3.5. Lợi ích tích hợp lớn hơn chi phí duy trì hợp đồng

Mỗi event được externalize tạo ra trách nhiệm vận hành: quản lý schema, phân quyền, retry, idempotency, giám sát backlog, lưu trữ và hỗ trợ consumer. Chỉ công bố event khi lợi ích của việc tách rời consumer xứng đáng với chi phí đó.

## 4. Những event thường không nên externalize

Một số event có thể hữu ích trong ứng dụng nhưng không nên trở thành hợp đồng tích hợp.

**Event điều phối nội bộ.** Ví dụ, một module phát tín hiệu để module khác trong cùng ứng dụng làm mới projection hoặc cập nhật cache. Nếu không có consumer bên ngoài, externalize chỉ làm tăng số message và phụ thuộc vận hành.

**Event kỹ thuật hoặc quá chi tiết.** Các tín hiệu như một phương thức đã chạy, một entity đã được lưu, một cache entry đã bị xóa hoặc một bước nội bộ đã hoàn tất thường gắn với implementation. Chúng có thể thay đổi thường xuyên và ít mang ý nghĩa cho hệ thống khác.

**Event chưa có ngữ nghĩa ổn định.** Trạng thái thử nghiệm, bước xử lý tạm thời hoặc kết quả trung gian chưa phải cam kết nghiệp vụ. Công bố chúng sẽ khiến consumer phụ thuộc vào chi tiết mà publisher chưa sẵn sàng duy trì.

**Event chứa dữ liệu nhạy cảm vượt nhu cầu.** Không gửi toàn bộ hồ sơ khách hàng, thông tin xác thực, dữ liệu thanh toán hoặc dữ liệu cá nhân chỉ vì object nội bộ có các trường đó. Nếu consumer cần một phần thông tin, hãy thiết kế payload tối thiểu và cơ chế truy cập có kiểm soát.

**Event quá lớn hoặc có tần suất quá cao.** Một event chứa hàng nghìn bản ghi hoặc được phát cho từng thay đổi nhỏ có thể làm tăng tải broker, chi phí lưu trữ và độ trễ consumer. Hãy cân nhắc gom nhóm, gửi tham chiếu, snapshot có giới hạn hoặc một kênh dữ liệu chuyên dụng.

**Command được đặt tên như event.** “Yêu cầu hoàn tiền” biểu đạt ý định yêu cầu một hành động; “Khoản hoàn tiền đã được thực hiện” biểu đạt sự thật đã xảy ra. Hai thông điệp có ngữ nghĩa, xử lý lỗi và quyền sở hữu khác nhau. Không nên externalize command dưới dạng event chỉ để tận dụng cùng một cơ chế.

## 5. Chọn ranh giới dữ liệu của integration event

Khi đã xác định event cần externalize, thiết kế payload như một hợp đồng công khai. Không tuần tự hóa trực tiếp entity ORM, aggregate hoặc object nội bộ có liên kết đến nhiều module.

Một payload thường nên có:

| Thành phần | Mục đích |
|---|---|
| Event ID ổn định | Nhận diện một lần phát và hỗ trợ chống xử lý trùng |
| Event type | Cho biết ngữ nghĩa của thông điệp |
| Schema version | Xác định cấu trúc payload consumer cần đọc |
| Aggregate/business ID | Xác định đối tượng nghiệp vụ liên quan |
| Occurred at | Thời điểm sự thật nghiệp vụ xảy ra |
| Correlation/causation ID nếu cần | Liên kết chuỗi công việc và nguyên nhân phát sinh |
| Các thuộc tính nghiệp vụ tối thiểu | Giúp consumer xử lý mà không phụ thuộc object nội bộ |

Ví dụ một hợp đồng đơn hàng:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record OrderConfirmed(
    UUID eventId,
    UUID orderId,
    Instant occurredAt,
    int schemaVersion,
    BigDecimal total,
    String currency
) {}
~~~

Payload trên cung cấp định danh, thời điểm và số tiền tổng. Nếu hệ thống kho cần danh sách mặt hàng, hãy thêm một cấu trúc dòng hàng có schema ổn định hoặc cung cấp một cách truy vấn được kiểm soát. Không nên đưa toàn bộ object Order chứa quan hệ ORM, thông tin nội bộ hoặc dữ liệu không liên quan vào message.

### Không để hợp đồng phụ thuộc vào model nội bộ

Tránh các trường như:

- Tên class Java hoặc package nội bộ được dùng như định danh nghiệp vụ.
- Trạng thái ORM, lazy proxy hoặc thông tin persistence.
- ID database chỉ có ý nghĩa trong một môi trường triển khai.
- Toàn bộ object graph được serialize tự động.
- Giá trị enum nội bộ mà consumer không có quy tắc xử lý khi xuất hiện giá trị mới.

Định danh nghiệp vụ cần ổn định qua môi trường và thời gian. Nếu event mang mã tham chiếu, hãy xác định rõ phạm vi duy nhất của mã đó.

## 6. Bảo vệ dữ liệu và quyền công bố

Externalization mở rộng phạm vi truy cập dữ liệu. Trước khi công bố, hãy phân loại từng trường theo mục đích sử dụng và consumer được phép nhận.

Các nguyên tắc cần áp dụng:

- Chỉ gửi trường cần thiết cho consumer đã xác định.
- Không gửi mật khẩu, token, secret, thông tin thẻ hoặc dữ liệu xác thực.
- Hạn chế dữ liệu cá nhân; nếu chỉ cần định danh khách hàng, gửi customer ID thay vì toàn bộ hồ sơ.
- Nếu cần thuộc tính nhạy cảm, xác định căn cứ nghiệp vụ, quyền truy cập, thời gian lưu và cách mã hóa phù hợp.
- Phân quyền topic, queue hoặc destination theo producer và consumer.
- Không ghi toàn bộ payload nhạy cảm vào log, trace hoặc dashboard.
- Xác định thời gian lưu message và quy trình xóa theo chính sách dữ liệu.

Cần nhớ rằng message có thể tồn tại trong broker, bản sao lưu, dead-letter queue và log của consumer. Xóa bản ghi trong database publisher không đồng nghĩa dữ liệu đã được xóa khỏi toàn bộ đường truyền.

## 7. Quyết định thời điểm phát và bảo đảm giao nhận

Một integration event nên phản ánh trạng thái nghiệp vụ đã được commit. Ví dụ, **OrderConfirmed** không nên được consumer hiểu là đơn hàng đã xác nhận nếu transaction cập nhật đơn hàng vẫn có thể rollback.

Với Spring Modulith, publisher có thể phát application event trong transaction nghiệp vụ; cấu hình publication registry và externalization cần bảo đảm publication được ghi nhận theo transaction boundary phù hợp. Sau khi transaction commit, cơ chế externalization chuyển event đến đích đã cấu hình. Cách cấu hình cụ thể phụ thuộc phiên bản Spring Modulith và adapter transport của ứng dụng.

Một minh họa đánh dấu event cần externalize:

~~~java
import org.springframework.modulith.events.Externalized;

@Externalized("orders")
public record OrderConfirmed(
    UUID eventId,
    UUID orderId,
    Instant occurredAt,
    int schemaVersion
) {}
~~~

Publisher phát event trong luồng nghiệp vụ:

~~~java
@Service
class ConfirmOrder {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;

    ConfirmOrder(OrderRepository orders, ApplicationEventPublisher events) {
        this.orders = orders;
        this.events = events;
    }

    @Transactional
    public void confirm(UUID orderId) {
        Order order = orders.findById(orderId).orElseThrow();
        order.confirm();

        events.publishEvent(new OrderConfirmed(
            UUID.randomUUID(),
            orderId,
            Instant.now(),
            1
        ));
    }
}
~~~

Ví dụ cho thấy event được phát trong transaction cập nhật đơn hàng và được đánh dấu là event externalized. Đích **orders** chỉ là tên minh họa; cần cấu hình transport và destination tương ứng trong ứng dụng. Annotation không tự tạo ra một broker hoặc thay thế cấu hình kết nối, bảo mật và retry.

Không nên kết luận rằng một lần gọi publish event đồng nghĩa consumer đã nhận và xử lý thành công. Cần phân biệt các mốc:

1. Publisher tạo application event.
2. Publication được ghi nhận trong transaction theo cấu hình registry.
3. Transaction nghiệp vụ commit.
4. Externalizer gửi message đến transport.
5. Broker xác nhận tiếp nhận theo mức bảo đảm đã cấu hình.
6. Consumer nhận và xử lý message.
7. Consumer ghi nhận kết quả xử lý.

Các mốc này có thể thất bại độc lập. Publication registry, retry và cơ chế quan sát giúp phát hiện, phục hồi các bước chưa hoàn tất; chúng không biến toàn bộ chuỗi thành một transaction phân tán nguyên tử.

## 8. Chọn chiến lược định tuyến và nhóm event

Định tuyến nên phản ánh ranh giới nghiệp vụ và quyền sở hữu. Không nên tạo một topic chung cho mọi loại event nếu consumer cần quyền truy cập, retention hoặc tải xử lý khác nhau.

Có thể phân nhóm theo:

- **Domain sở hữu:** orders, payments, invoices, inventory.
- **Mục đích consumer:** fulfillment, accounting, analytics.
- **Mức độ nhạy cảm:** public integration data và restricted data.
- **Tải và thứ tự:** event cần thứ tự theo aggregate có thể cần partition key tương ứng.
- **Vòng đời hợp đồng:** nhóm event có lịch phát hành và chính sách tương thích tương tự.

Không nên tạo destination riêng cho từng class một cách máy móc. Quá nhiều topic/queue làm tăng cấu hình, ACL, cảnh báo và chi phí vận hành. Cũng không nên gom các event không liên quan vào một kênh nếu điều đó khiến consumer phải đọc dữ liệu không cần thiết hoặc nhận quyền quá rộng.

Nếu consumer cần thứ tự theo đơn hàng, hãy xác định khóa phân vùng dựa trên order ID và kiểm tra khả năng bảo đảm thứ tự của transport. Thứ tự toàn cục giữa mọi event thường đắt và không cần thiết. Timestamp cũng không thay thế một cơ chế thứ tự hoặc version nghiệp vụ.

## 9. Quản lý phiên bản hợp đồng

Consumer có thể nâng cấp chậm hơn publisher. Vì vậy, thay đổi payload phải được đánh giá theo khả năng tương thích.

Các thay đổi thường ít rủi ro hơn nếu consumer được thiết kế phù hợp:

- Thêm trường tùy chọn có giá trị mặc định rõ ràng.
- Thêm metadata mà consumer cũ có thể bỏ qua.
- Mở rộng enum khi consumer có nhánh xử lý giá trị không nhận biết.

Các thay đổi có nguy cơ phá vỡ consumer:

- Đổi tên hoặc xóa trường đang được sử dụng.
- Thay đổi kiểu dữ liệu hoặc đơn vị đo.
- Đổi ngữ nghĩa của trường nhưng giữ nguyên tên.
- Đổi ý nghĩa event hoặc điều kiện phát.
- Chuyển từ snapshot sang delta mà không công bố rõ.
- Đổi cách diễn giải múi giờ, tiền tệ hoặc giá trị null.

Khi cần thay đổi không tương thích, hãy công bố hợp đồng mới có phiên bản hoặc event type mới, hỗ trợ giai đoạn chuyển tiếp và có kế hoạch ngừng hợp đồng cũ. Không dựa vào tên class Java làm chiến lược version duy nhất nếu consumer độc lập với codebase.

Đối với tiền tệ, đơn vị đo và thời gian, phải ghi rõ quy ước. Ví dụ, số tiền cần đi kèm currency; thời điểm nên có timezone/offset hoặc quy ước UTC; số lượng cần xác định đơn vị. Một payload hợp lệ về cú pháp vẫn có thể gây lỗi nghiệp vụ nếu ngữ nghĩa không rõ.

## 10. Retry, idempotency và xử lý lỗi ở consumer

Message có thể được gửi lại khi publisher không nhận được xác nhận, transport tạm thời gián đoạn hoặc consumer lỗi sau khi nhận message. Vì vậy, consumer nên giả định cùng một event có thể xuất hiện nhiều lần.

Một consumer có thể ghi nhận event ID đã xử lý bằng một ràng buộc duy nhất trong transaction cùng với thay đổi nghiệp vụ:

~~~java
@Transactional
public void handle(OrderConfirmed event) {
    if (processedEvents.existsById(event.eventId())) {
        return;
    }

    inventory.reserveFor(event.orderId());
    processedEvents.save(new ProcessedEvent(event.eventId()));
}
~~~

Đây là ví dụ khái niệm. Trong triển khai thực tế, thao tác kiểm tra và ghi nhận event ID cần được bảo vệ trước xử lý đồng thời, thường bằng khóa duy nhất ở database và cách xử lý xung đột phù hợp. Nếu consumer gọi API bên ngoài, hãy dùng idempotency key nếu dịch vụ đích hỗ trợ.

Cần phân loại lỗi:

- Lỗi tạm thời như timeout, broker mất kết nối hoặc downstream quá tải: có thể retry với backoff.
- Lỗi dữ liệu hoặc schema không hợp lệ: retry vô hạn thường không giải quyết được; cần cách ly và điều tra.
- Lỗi nghiệp vụ không thể tự phục hồi: đưa vào luồng xử lý ngoại lệ hoặc dead-letter phù hợp.
- Lỗi cấu hình và quyền truy cập: cảnh báo rõ ràng, tránh retry dày đặc làm tăng tải.

Retry cần có giới hạn, khoảng chờ và chính sách xử lý sau khi vượt giới hạn. Khi phát lại message từ dead-letter queue, cần giữ event ID và metadata đủ để truy vết.

## 11. Quan sát luồng externalization

Một event đã được đánh dấu externalized nhưng chưa đến consumer là một vấn đề giao nhận cần nhìn thấy được. Hãy theo dõi cả phía publisher, transport và consumer.

| Chỉ số | Điều cần phát hiện |
|---|---|
| Số publication externalized chưa hoàn tất | Event đang chờ hoặc bị kẹt ở publisher |
| Tuổi của publication cũ nhất | Thời gian chậm giao tăng bất thường |
| Tỷ lệ gửi lỗi và retry | Transport hoặc cấu hình destination có vấn đề |
| Backlog, throughput và dead-letter của broker | Khả năng tiếp nhận và xử lý của transport |
| Tỷ lệ lỗi theo event type/consumer | Hợp đồng hoặc logic xử lý có vấn đề |
| Độ trễ từ occurredAt đến consumer processedAt | Thời gian event đi qua toàn bộ luồng |
| Số event trùng và event bị bỏ qua do idempotency | Mức độ lặp lại và hiệu quả chống xử lý trùng |

Dùng event ID, correlation ID, causation ID và consumer name để liên kết log, metric và trace. Không log payload đầy đủ nếu payload có dữ liệu nhạy cảm. Cảnh báo nên dựa trên tuổi publication cũ nhất, tốc độ tăng backlog và tỷ lệ lỗi, thay vì chỉ dựa vào tổng số message.

## 12. Quy trình quyết định trước khi externalize

Có thể dùng quy trình sau cho mỗi loại event:

1. **Xác định sự thật nghiệp vụ:** viết một câu mô tả chính xác điều đã xảy ra và điều kiện để nó được xem là hoàn tất.
2. **Nêu consumer:** chỉ ra hệ thống hoặc tổ chức nào cần biết sự thật đó và hành động của họ.
3. **Kiểm tra phạm vi:** nếu chỉ có thành phần nội bộ cần event, giữ nó ở application event nội bộ.
4. **Thiết kế hợp đồng:** chọn event type, định danh, thời điểm, schema version và trường tối thiểu.
5. **Rà soát dữ liệu:** loại bỏ trường nhạy cảm hoặc không cần thiết; xác định quyền truy cập và retention.
6. **Chọn destination:** nhóm event theo domain, consumer, tải và chính sách vận hành.
7. **Xác định bảo đảm giao nhận:** transaction boundary, publication registry, retry, idempotency, thứ tự và dead-letter.
8. **Thống nhất vòng đời:** xác định owner, quy tắc tương thích, cách thông báo thay đổi và kế hoạch ngừng hợp đồng.
9. **Kiểm chứng với consumer:** xác nhận consumer hiểu ngữ nghĩa, xử lý message lặp và xử lý schema mới/cũ.
10. **Đưa vào quan sát:** theo dõi publication, transport, backlog, lỗi và độ trễ sau khi triển khai.

Sơ đồ quyết định rút gọn:

~~~mermaid
flowchart TD
    A[Application event được phát] --> B{Có consumer ngoài ứng dụng?}
    B -- Không --> C[Giữ event nội bộ]
    B -- Có --> D{Biểu đạt sự thật nghiệp vụ ổn định?}
    D -- Không --> E[Thiết kế lại ngữ nghĩa hoặc giữ nội bộ]
    D -- Có --> F{Consumer có thể xử lý bất đồng bộ?}
    F -- Không --> G[Xem xét API hoặc command đồng bộ]
    F -- Có --> H[Rà soát payload và dữ liệu nhạy cảm]
    H --> I{Hợp đồng tối thiểu và an toàn?}
    I -- Không --> J[Thu gọn hoặc bảo vệ payload]
    I -- Có --> K[Chọn destination và chính sách giao nhận]
    K --> L[Externalize và giám sát]
~~~

## 13. Ví dụ quyết định: đơn hàng được xác nhận

Giả sử module Đơn hàng phát event sau khi đơn được xác nhận. Hệ thống có ba consumer: Kho chuẩn bị hàng, Hóa đơn phát hành chứng từ và Phân tích cập nhật số liệu.

Event đáng externalize là **OrderConfirmed** vì nó thể hiện một cam kết nghiệp vụ mà ba consumer đều cần biết. Hợp đồng có thể chứa:

- event ID và order ID;
- thời điểm xác nhận;
- các dòng hàng gồm product ID và số lượng nếu Kho cần chúng;
- tổng tiền và currency nếu Hóa đơn hoặc Phân tích cần;
- schema version và correlation ID khi cần truy vết.

Các trường như ghi chú nội bộ, thông tin đăng nhập, toàn bộ lịch sử thay đổi, trạng thái ORM hoặc thông tin thẻ thanh toán không thuộc hợp đồng này.

Nếu kho chỉ cần order ID và có API truy vấn đơn hàng được kiểm soát, payload có thể chỉ mang định danh. Nếu kho không thể truy vấn hệ thống Đơn hàng, cần cung cấp dữ liệu đủ để xử lý trong event. Đây là quyết định hợp đồng dựa trên nhu cầu consumer, không phải quyết định dựa trên object nào thuận tiện để serialize.

Một event khác như **OrderValidationStepCompleted** có thể chỉ phục vụ workflow nội bộ. Nếu không có consumer bên ngoài cần bước kỹ thuật đó, không externalize. Khi hệ thống sau này có nhu cầu tích hợp mới, hãy tạo hoặc chuyển đổi sang một integration event có ngữ nghĩa phù hợp, thay vì công bố nguyên trạng event nội bộ.

## 14. Checklist rà soát

Trước khi gắn cơ chế externalization cho event, hãy xác nhận:

- [ ] Có ít nhất một consumer bên ngoài được xác định rõ.
- [ ] Event mô tả một sự thật nghiệp vụ đã xảy ra, không phải chỉ thị yêu cầu hành động.
- [ ] Module sở hữu dữ liệu chịu trách nhiệm phát event.
- [ ] Tên và ngữ nghĩa event đủ rõ để consumer hiểu độc lập.
- [ ] Payload có định danh, thời điểm và trường nghiệp vụ tối thiểu cần thiết.
- [ ] Payload không phụ thuộc entity ORM, package nội bộ hoặc ID chỉ có ý nghĩa cục bộ.
- [ ] Dữ liệu nhạy cảm đã được loại bỏ hoặc có biện pháp bảo vệ và phân quyền phù hợp.
- [ ] Destination, quyền truy cập và retention đã được xác định.
- [ ] Transaction boundary và publication registry được cấu hình phù hợp.
- [ ] Consumer có idempotency và chính sách xử lý lỗi/retry.
- [ ] Có quy tắc versioning và tương thích schema.
- [ ] Có metric, log và cảnh báo cho publication chưa hoàn tất, backlog và dead-letter.

## 15. Nguyên tắc lựa chọn

Hãy externalize event khi nó công bố một sự thật nghiệp vụ ổn định mà một consumer bên ngoài thực sự cần biết và có thể xử lý bất đồng bộ. Thiết kế integration event như hợp đồng độc lập, chỉ mang dữ liệu cần thiết, có owner và có chính sách tương thích.

Giữ event nội bộ khi nó chỉ điều phối thành phần trong ứng dụng, phản ánh chi tiết kỹ thuật hoặc chưa có ngữ nghĩa đủ ổn định. Khi ranh giới và hợp đồng được chọn đúng, Spring Modulith có thể giúp kết nối application event với cơ chế externalization, còn publication registry, retry, idempotency và quan sát giúp vận hành việc giao nhận đáng tin cậy qua ranh giới hệ thống.
