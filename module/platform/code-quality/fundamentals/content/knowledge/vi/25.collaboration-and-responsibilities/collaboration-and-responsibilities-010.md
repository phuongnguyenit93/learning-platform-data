# Dùng sự cố và khó khăn bảo trì làm đầu vào cải thiện

Một dịch vụ gửi thông báo đơn hàng hoạt động bình thường trong nhiều tuần. Sau một đợt gián đoạn mạng, message broker phát lại một số message chưa được xác nhận. Khách hàng nhận cùng một thông báo hai lần. Nhóm xử lý sự cố bằng cách khởi động lại consumer và giảm tốc độ nhận message. Hệ thống ổn định trở lại, nhưng vài tuần sau tình trạng lặp lại.

Nếu chỉ ghi nhận “đã khởi động lại consumer thành công”, nhóm đã xử lý triệu chứng trước mắt mà chưa học được vì sao một message được xử lý lặp. Nếu điều tra sâu hơn, có thể phát hiện consumer chưa có cơ chế idempotency, test không mô phỏng redelivery và dashboard không hiển thị tỷ lệ xử lý trùng.

**Sự cố và khó khăn bảo trì là dữ liệu phản hồi về chất lượng của hệ thống.** Chúng cho biết những giả định nào đã không đúng, ranh giới nào khó hiểu, kiểm thử nào chưa đủ và quy trình nào đang làm công việc thường ngày trở nên tốn kém.

Trong module **CODE_QUALITY_FUNDAMENTALS**, chúng ta tìm hiểu những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi** hay không. Ở chương **Cộng tác và trách nhiệm**, việc dùng sự cố và khó khăn bảo trì làm đầu vào cải thiện giúp nhóm biến kinh nghiệm vận hành thành thay đổi cụ thể trong code, test, tài liệu, observability và quy trình làm việc.

Bài học này trình bày cách học từ sự cố mà không đổ lỗi cá nhân, nhận diện ma sát bảo trì trước khi chúng trở thành sự cố, chọn hành động có tác động và kiểm tra xem cải thiện có thực sự hiệu quả hay không.

## 1. Sự cố và khó khăn bảo trì nói lên điều gì?

**Sự cố (incident)** là một sự kiện làm dịch vụ, dữ liệu, bảo mật hoặc trải nghiệm người dùng suy giảm so với mức mong đợi. Sự cố có thể là gián đoạn lớn, lỗi một phần, mất dữ liệu, xử lý sai giao dịch hoặc một lần suýt gây ảnh hưởng nhưng được phát hiện kịp thời.

**Khó khăn bảo trì (maintenance friction)** là chi phí hoặc trở ngại lặp lại khi nhóm cần hiểu, sửa, kiểm thử, triển khai hay vận hành hệ thống. Nó có thể chưa gây outage, nhưng làm mỗi thay đổi chậm hơn và tăng xác suất sai sót.

| Nguồn tín hiệu | Ví dụ | Điều có thể cần cải thiện |
| --- | --- | --- |
| Sự cố production | Consumer xử lý cùng một event hai lần. | Idempotency, transaction boundary, test redelivery. |
| Lỗi hồi quy | Sửa chính sách giá ở một luồng nhưng quên luồng khác. | Nơi sở hữu quy tắc, contract test, loại bỏ sao chép sai khái niệm. |
| Near miss | Một secret được phát hiện trong PR trước khi phát hành. | Secret scanning, quy trình xử lý credential và hướng dẫn developer. |
| Hỗ trợ khách hàng | Người dùng thường xuyên không hiểu vì sao thao tác bị từ chối. | Thông báo lỗi, tài liệu và hợp đồng API. |
| Khó điều tra | Mất 90 phút mới xác định được request đi qua service nào. | Correlation ID, trace, log có ngữ cảnh và ownership. |
| Test khó viết | Một thay đổi nhỏ phải khởi động nhiều dịch vụ thật. | Ranh giới phụ thuộc, fixture và test architecture. |
| Build chậm | Developer phải chờ cả suite dài để phát hiện lỗi biên đơn giản. | Phân tầng test và tối ưu pipeline. |
| Thao tác thủ công lặp | Mỗi lần release phải sửa config trực tiếp trên máy chủ. | Automation, review cấu hình và quy trình triển khai. |
| Tri thức tập trung | Chỉ một người biết cách khôi phục một loại dữ liệu. | Runbook, quyền sở hữu và diễn tập chuyển giao. |

Không phải mọi khó khăn đều là lỗi thiết kế mã nguồn. Có thể nguyên nhân nằm ở môi trường, quyền truy cập, công cụ, phân công hoặc quy trình. Nhưng tất cả đều là **tín hiệu đáng điều tra** nếu chúng ảnh hưởng tới khả năng thay đổi và độ tin cậy của sản phẩm.

## 2. Phân biệt triệu chứng, nguyên nhân gần và điều kiện góp phần

Khi có sự cố, nhóm thường nhìn thấy một triệu chứng rõ ràng trước:

- API trả 500.
- Queue tăng liên tục.
- Một giao dịch bị xử lý hai lần.
- Một nhóm người dùng không đăng nhập được.
- Database hết connection.
- Bản phát hành phải rollback.

Triệu chứng cho biết **điều gì đã xảy ra**, nhưng chưa giải thích vì sao hệ thống cho phép nó xảy ra.

Có thể phân tích theo các lớp:

| Lớp | Câu hỏi | Ví dụ trong sự cố message lặp |
| --- | --- | --- |
| **Tác động** | Người dùng hoặc hệ thống bị ảnh hưởng thế nào? | Một số khách hàng nhận hai email xác nhận. |
| **Triệu chứng** | Quan sát được điều gì? | Consumer gửi cùng nội dung nhiều lần. |
| **Nguyên nhân gần (proximate cause)** | Sự kiện trực tiếp nào kích hoạt? | Broker redeliver message sau khi không nhận được acknowledgment. |
| **Điều kiện góp phần** | Điều gì làm sự kiện có thể gây tác động? | Consumer gửi email trước khi ghi trạng thái hoàn tất. |
| **Lỗ hổng kiểm soát** | Vì sao hệ thống không ngăn hoặc phát hiện sớm? | Không có idempotency key và metric duplicate delivery. |
| **Yếu tố hệ thống** | Bối cảnh nào làm vấn đề dễ xuất hiện? | Retry là một phần thiết kế nhưng chưa có hợp đồng xử lý lặp xuyên suốt. |

Không nên dừng ở một câu như “do broker gửi lại message”. Redelivery có thể là hành vi bình thường của hệ thống message delivery. Câu hỏi quan trọng hơn là **consumer có được thiết kế để chịu được việc gửi lại hay không**.

Cũng không nên cố tìm một “nguyên nhân gốc duy nhất” cho mọi sự cố. Một sự cố thường xuất hiện khi nhiều điều kiện cùng hội tụ: thay đổi code, cấu hình, dữ liệu, tải, dependency, công cụ giám sát và cách con người tương tác với hệ thống.

## 3. Học từ sự cố theo cách không đổ lỗi

Một buổi review sự cố hữu ích tập trung vào **hệ thống đã được thiết kế, triển khai và vận hành như thế nào trong bối cảnh thực tế**.

Cách hỏi có tính buộc tội:

- Ai đã quên kiểm tra?
- Vì sao người đó không biết?
- Sao lại triển khai vào thời điểm đó?
- Ai chịu trách nhiệm cho outage?

Những câu hỏi này thường dẫn tới câu trả lời cá nhân và ít làm rõ điều kiện hệ thống.

Cách hỏi có ích hơn:

- Người thực hiện nhìn thấy thông tin nào tại thời điểm quyết định?
- Hướng dẫn và công cụ lúc đó khuyến khích hành động nào?
- Hệ thống có cảnh báo trước khi tác động lan rộng không?
- Có điều kiện nào khiến một hành động hợp lý lại tạo ra kết quả không mong muốn?
- Một kiểm soát nào có thể giúp người khác phát hiện hoặc ngăn tình huống tương tự?

**Blameless (không đổ lỗi)** không có nghĩa là bỏ qua trách nhiệm. Nhóm vẫn cần xác định owner, hành động khắc phục và thời hạn. Điểm khác biệt là phân tích điều kiện và cơ chế thay vì quy toàn bộ vấn đề cho một cá nhân.

Nếu một thao tác nguy hiểm có thể được thực hiện chỉ bằng một lệnh không có xác nhận, đó là cơ hội cải thiện guardrail. Nếu một thay đổi không có reviewer phù hợp, cần xem lại chính sách review và ownership. Nếu một cá nhân cố ý vi phạm quy trình đã rõ, tổ chức vẫn có thể xử lý trách nhiệm theo quy định riêng; post-incident learning không thay thế quản trị nhân sự.

## 4. Tạo timeline từ bằng chứng, không từ trí nhớ

Timeline giúp mọi người thống nhất **trình tự sự kiện**. Hãy ghi thời gian, quan sát và nguồn bằng chứng:

| Thời điểm | Sự kiện | Nguồn kiểm chứng |
| --- | --- | --- |
| 09:02 | Bản phát hành mới bắt đầu triển khai. | Deployment record. |
| 09:05 | Consumer bắt đầu nhận event từ partition liên quan. | Application log và trace. |
| 09:08 | Kết nối tới notification provider chập chờn. | Dependency metric và provider status. |
| 09:09 | Một số message không được xác nhận đúng thời hạn. | Broker metric. |
| 09:10 | Broker redeliver các message đó. | Message metadata và consumer log. |
| 09:12 | Duplicate notification tăng. | Dashboard và báo cáo khách hàng. |
| 09:18 | Nhóm giảm tốc độ consumer để hạn chế tác động. | Incident channel và deployment/config record. |
| 09:27 | Tỷ lệ duplicate giảm; hàng đợi vẫn còn backlog. | Dashboard. |
| 10:03 | Backlog được xử lý hết và dịch vụ ổn định. | Queue depth và synthetic check. |

Đây là **timeline giả định để minh họa**, không phải lịch sử của một hệ thống thực tế.

Khi xây timeline:

- Dùng timestamp có timezone thống nhất.
- Phân biệt thời điểm sự kiện xảy ra với thời điểm log được ghi hoặc nhận.
- Ghi nguồn dữ liệu để người khác kiểm tra lại.
- Đánh dấu khoảng thời gian chưa đủ bằng chứng.
- Không biến phỏng đoán thành sự kiện đã xác nhận.
- Không đưa credential, dữ liệu cá nhân hoặc payload nhạy cảm vào báo cáo rộng rãi.

Nếu đồng hồ các service lệch nhau, hãy ghi nhận độ lệch và dùng trace/correlation ID để nối các sự kiện. Một timeline chính xác giúp tránh tranh luận dựa trên trí nhớ khác nhau.

## 5. Thu thập bằng chứng đủ rộng nhưng có mục đích

Một cuộc điều tra thường cần nhiều loại dữ liệu:

| Nguồn | Có thể trả lời câu hỏi gì? | Giới hạn cần nhớ |
| --- | --- | --- |
| Application log | Lỗi nào được ghi, request/event nào liên quan? | Log thiếu correlation hoặc ghi sai mức có thể gây nhiễu. |
| Metrics | Tỷ lệ lỗi, latency, queue, CPU, memory biến động ra sao? | Tổng hợp có thể che khuất một nhóm nhỏ bị ảnh hưởng. |
| Distributed trace | Request đi qua service nào và chậm ở đâu? | Sampling có thể không giữ mọi trace. |
| Deployment/config history | Thay đổi nào diễn ra trước sự cố? | Tương quan thời gian không chứng minh quan hệ nhân quả. |
| Database/audit record | Trạng thái dữ liệu thay đổi thế nào? | Cần bảo vệ quyền truy cập và dữ liệu nhạy cảm. |
| Test report | Test nào đã chạy, test nào bị bỏ qua hoặc flaky? | Test xanh không chứng minh mọi hợp đồng đều được kiểm tra. |
| PR/review record | Giả định, quyết định và phạm vi thay đổi là gì? | Không dùng lịch sử review để quy lỗi cá nhân. |
| Support ticket | Người dùng gặp tác động cụ thể nào? | Báo cáo người dùng có thể thiếu chi tiết kỹ thuật. |
| Runbook/incident notes | Nhóm đã làm gì để giảm tác động? | Hướng dẫn có thể lỗi thời hoặc không khớp môi trường. |

Hãy thu thập bằng chứng để kiểm tra **giả thuyết cụ thể**. Không cần tải toàn bộ dữ liệu production về máy cá nhân hoặc sao chép payload thật vào ticket nếu chỉ cần event ID đã được che/mã hóa.

## 6. Post-incident review: từ sự cố tới bài học

Sau khi hệ thống ổn định, nhóm có thể tổ chức **post-incident review** hoặc viết postmortem. Tài liệu không nhằm kể lại mọi thao tác theo thứ tự mà cần giúp người đọc hiểu:

1. Tác động là gì và kéo dài bao lâu?
2. Điều gì đã xảy ra?
3. Vì sao hệ thống cho phép tác động xuất hiện?
4. Điều gì giúp phát hiện và giảm thiểu?
5. Điều gì làm quá trình điều tra hoặc phục hồi chậm?
6. Hành động nào có thể giảm xác suất tái diễn hoặc giảm tác động lần sau?
7. Ai sở hữu hành động và bằng chứng hoàn tất là gì?

Một cấu trúc đơn giản:

~~~markdown
# Post-incident review: xử lý message bị lặp

## Tóm tắt
Consumer phát lại một số notification sau khi broker redeliver message.

## Tác động
- Một nhóm khách hàng nhận email xác nhận trùng.
- Không phát hiện giao dịch thanh toán bị thực hiện trùng.
- Dịch vụ gửi thông báo bị backlog trong khoảng thời gian xác định.

## Timeline
- Ghi các mốc đã xác minh cùng nguồn log/metric.

## Điều kiện góp phần
- Consumer không có cơ chế idempotency bền vững.
- Trạng thái hoàn tất được ghi sau tác dụng phụ.
- Test chưa mô phỏng redelivery và retry.
- Dashboard không theo dõi tỷ lệ xử lý trùng.

## Điều giúp giảm tác động
- Queue depth và error rate có cảnh báo.
- Nhóm có thể giảm tốc độ consumer mà không dừng toàn bộ hệ thống.

## Hành động
- Bổ sung idempotency theo event ID.
- Kiểm thử redelivery và crash/retry.
- Thêm metric duplicate và cảnh báo.
- Cập nhật runbook xử lý backlog.

## Owner và thời hạn
- Ghi rõ người/nhóm sở hữu, hạn và tiêu chí hoàn tất.
~~~

Đây là mẫu để điều chỉnh. Báo cáo nên ngắn đủ để người liên quan đọc, nhưng có liên kết tới bằng chứng kỹ thuật cần thiết.

## 7. Phân biệt hành động khắc phục tức thời và cải thiện lâu dài

Trong sự cố, nhóm thường cần hành động nhanh để giảm tác động:

- Rollback bản phát hành.
- Tắt feature flag.
- Giảm tốc độ consumer.
- Chuyển traffic sang vùng khác.
- Thu hồi credential bị lộ.
- Khôi phục dữ liệu từ backup.

Đó là **mitigation (giảm thiểu)** hoặc recovery. Nó có thể cần thiết ngay cả khi chưa hiểu hết nguyên nhân.

Sau đó cần phân biệt:

| Loại hành động | Mục đích | Ví dụ |
| --- | --- | --- |
| **Mitigation** | Giảm tác động hiện tại. | Tạm dừng consumer đang gửi thông báo trùng. |
| **Correction** | Khôi phục hành vi đúng trong tình huống cụ thể. | Xử lý các notification đã bị gửi sai hoặc backlog. |
| **Prevention** | Giảm khả năng sự cố tái diễn. | Thiết kế idempotency và xử lý redelivery. |
| **Detection** | Phát hiện sớm khi sự cố bắt đầu. | Metric duplicate và alert theo ngưỡng. |
| **Recovery readiness** | Giảm thời gian khôi phục. | Runbook, replay an toàn và diễn tập. |
| **Learning/process improvement** | Giảm khoảng trống trong cách làm việc. | Bổ sung checklist thay đổi consumer và owner cho test tích hợp. |

Chỉ restart service có thể là mitigation hợp lý, nhưng **không phải bằng chứng rằng vấn đề đã được sửa**. Tương tự, thêm một alert không ngăn sự cố; nó chỉ giúp phát hiện sớm hơn. Một kế hoạch tốt có thể cần cả prevention, detection và recovery.

## 8. Chuyển bài học thành thay đổi trong code và test

Một phát hiện sau sự cố nên được diễn đạt thành **điều kiện có thể kiểm chứng**.

Ví dụ:

| Phát hiện | Hành động mơ hồ | Hành động có thể kiểm chứng |
| --- | --- | --- |
| Message có thể được gửi lại. | “Cải thiện consumer.” | Với cùng event ID được giao nhiều lần, chỉ tạo một tác dụng phụ theo hợp đồng idempotency. |
| Test không kiểm tra ngưỡng. | “Viết thêm test.” | Thêm test dưới, tại và trên ngưỡng với expected độc lập từ chính sách. |
| Không biết request đi qua service nào. | “Thêm logging.” | Propagate correlation ID qua các service và có trace cho đường quan trọng. |
| Rollback phải sửa tay. | “Tự động hóa release.” | Có lệnh rollback được kiểm thử và runbook chỉ rõ điều kiện sử dụng. |
| Một người giữ kiến thức khôi phục. | “Chia sẻ kiến thức.” | Một thành viên khác thực hiện diễn tập theo runbook và hoàn thành không cần hướng dẫn riêng. |
| Test integration mất quá lâu. | “Tối ưu CI.” | Đo stage time, tách test nhanh và kiểm soát dependency dùng chung. |

Một action item tốt có:

- **Vấn đề cụ thể** được giải quyết.
- **Phạm vi** và hệ thống liên quan.
- **Owner** chịu trách nhiệm.
- **Thời hạn hoặc điểm xem lại** phù hợp.
- **Tiêu chí hoàn tất** có thể xác minh.
- **Liên kết với incident hoặc bằng chứng** đã phát hiện vấn đề.

Tránh action item như “cẩn thận hơn”, “review kỹ hơn” hoặc “không để xảy ra lần nữa”. Chúng không tạo ra cơ chế mới giúp con người và hệ thống làm đúng dễ hơn.

## 9. Ví dụ Java: xử lý message lặp bằng idempotency

Giả sử consumer nhận sự kiện xác nhận đơn hàng. Broker có thể giao lại cùng một event nếu consumer chưa xác nhận hoặc kết nối bị gián đoạn.

Một implementation đơn giản không có idempotency:

~~~java
public final class OrderConfirmationHandler {
    private final NotificationGateway gateway;

    public OrderConfirmationHandler(NotificationGateway gateway) {
        this.gateway = gateway;
    }

    public void handle(OrderConfirmed event) {
        gateway.send(event.orderId());
    }
}
~~~

Mỗi lần handle được gọi, một thông báo mới được gửi. Nếu cùng event được giao lại ba lần, gateway có thể nhận ba yêu cầu gửi.

Một cải thiện có thể dùng event ID ổn định làm idempotency key:

~~~java
public record OrderConfirmed(
        String eventId,
        String orderId) {
}

public interface NotificationGateway {
    // Hợp đồng: các lần gọi cùng key chỉ tạo một notification.
    void sendOnce(String idempotencyKey, String orderId);
}

public interface ProcessedEventStore {
    boolean isCompleted(String eventId);
    void markCompleted(String eventId);
}

public final class OrderConfirmationHandler {
    private final NotificationGateway gateway;
    private final ProcessedEventStore eventStore;

    public OrderConfirmationHandler(
            NotificationGateway gateway,
            ProcessedEventStore eventStore) {
        this.gateway = gateway;
        this.eventStore = eventStore;
    }

    public void handle(OrderConfirmed event) {
        if (eventStore.isCompleted(event.eventId())) {
            return;
        }

        gateway.sendOnce(event.eventId(), event.orderId());
        eventStore.markCompleted(event.eventId());
    }
}
~~~

Ví dụ này làm rõ hai hợp đồng:

- Event ID phải **ổn định qua các lần redelivery**.
- Notification gateway phải hỗ trợ **idempotency theo key**, nghĩa là gọi lại cùng key không tạo notification thứ hai.

Trong hệ thống thật, ProcessedEventStore cần lưu trạng thái bền vững và xử lý cạnh tranh một cách an toàn. Nếu hai consumer cùng xử lý một event, chỉ kiểm tra isCompleted rồi cùng gửi là chưa đủ. Gateway cũng phải thực sự đảm bảo idempotency theo key, với thời hạn lưu key phù hợp.

Nếu nhà cung cấp notification không hỗ trợ idempotency, cần thiết kế ranh giới lưu trữ và gửi tin phù hợp, chẳng hạn inbox/outbox, trạng thái xử lý có khóa duy nhất và quy trình retry/reconciliation. Không thể tuyên bố “exactly once” chỉ vì có một boolean trong bộ nhớ.

### Kiểm thử JUnit 5 cho hành vi redelivery

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.*;

import org.junit.jupiter.api.Test;

class OrderConfirmationHandlerTest {
    @Test
    void repeatedEventUsesSameIdempotencyKey() {
        var gateway = mock(NotificationGateway.class);
        var store = mock(ProcessedEventStore.class);
        var handler = new OrderConfirmationHandler(gateway, store);
        var event = new OrderConfirmed("evt-42", "order-9");

        when(store.isCompleted("evt-42"))
                .thenReturn(false, false);

        handler.handle(event);
        handler.handle(event);

        verify(gateway, times(2))
                .sendOnce("evt-42", "order-9");
        verify(store, times(2)).markCompleted("evt-42");
    }

    @Test
    void completedEventDoesNotCallGatewayAgain() {
        var gateway = mock(NotificationGateway.class);
        var store = mock(ProcessedEventStore.class);
        var handler = new OrderConfirmationHandler(gateway, store);
        var event = new OrderConfirmed("evt-42", "order-9");

        when(store.isCompleted("evt-42")).thenReturn(true);

        handler.handle(event);

        verifyNoInteractions(gateway);
        verify(store).isCompleted("evt-42");
        verify(store, never()).markCompleted("evt-42");
    }
}
~~~

Test đầu xác nhận handler dùng cùng idempotency key qua redelivery; **nó không tự chứng minh gateway bên ngoài đã gửi đúng một email**. Muốn chứng minh điều đó cần contract test hoặc integration test cho cơ chế deduplication của gateway, và test persistence cho event store.

Đây là ví dụ minh họa hợp đồng và hướng kiểm thử, không phải implementation hoàn chỉnh cho mọi message broker.

## 10. Khó khăn bảo trì là tín hiệu trước sự cố

Không cần chờ outage mới cải thiện hệ thống. Nhiều khó khăn lặp lại có thể báo hiệu một rủi ro đang tích lũy:

### Khó tìm nơi sở hữu quy tắc

Một chính sách nghiệp vụ nằm trong nhiều service. Developer phải tìm kiếm toàn repository và hỏi nhiều người trước khi đổi. Đây là tín hiệu về ownership hoặc trùng lặp khái niệm.

### Khó tạo test

Một hàm nghiệp vụ phải khởi động database, gọi HTTP và đọc clock hệ thống chỉ để kiểm tra một điều kiện. Đây có thể là dấu hiệu phụ thuộc bị trộn hoặc thiếu seam kiểm thử phù hợp.

### Khó biết thay đổi có an toàn không

Test suite chậm, flaky hoặc không có test ở các nhánh quan trọng. Developer ngại refactor vì không có bằng chứng giữ hành vi.

### Khó điều tra lỗi

Log không có correlation ID, thông báo chỉ ghi “operation failed”, dashboard không tách theo endpoint hoặc loại lỗi. Nhóm mất nhiều thời gian để xác định vùng xảy ra vấn đề.

### Khó triển khai và phục hồi

Release phụ thuộc thao tác thủ công, rollback không được thử, migration không có hướng xử lý khi chạy dở. Một thay đổi bình thường có thể trở thành sự kiện rủi ro cao.

### Khó chuyển giao

Một số bước chỉ tồn tại trong trí nhớ của một thành viên. Khi người đó vắng mặt, việc sửa hoặc khôi phục bị trì hoãn.

Những dấu hiệu này có thể trở thành **backlog cải thiện chất lượng** trước khi tạo sự cố lớn.

## 11. Thu thập maintenance friction một cách có hệ thống

Có thể ghi nhận ma sát bảo trì từ nhiều nguồn:

- Retrospective sau sprint.
- Code review và comment lặp lại.
- Ticket hỗ trợ developer.
- Build/CI report.
- Incident và near-miss review.
- On-call handover.
- Thời gian điều tra bug.
- Các thao tác thủ công trong release.
- Những thay đổi thường xuyên phải nhờ cùng một chuyên gia.

Một bảng ghi nhận đơn giản:

| Ngày/nhóm công việc | Ma sát quan sát được | Tần suất | Tác động | Bằng chứng |
| --- | --- | --- | --- | --- |
| Thêm một rule checkout | Phải sửa ba bản sao cùng công thức. | 4 lần trong 2 tháng | Tăng thời gian review, từng bỏ sót một luồng. | Các PR và bug liên quan. |
| Chạy test integration | Phải khởi động toàn bộ stack cho một unit logic. | Mỗi lần sửa module | Feedback chậm. | CI stage duration. |
| Điều tra timeout | Log không nối được request qua service. | 3 incident | Tăng thời gian tìm nguyên nhân. | Trace/log thiếu correlation. |
| Release migration | Cần một người chạy lệnh thủ công. | Mỗi release | Phụ thuộc người và tăng rủi ro thao tác. | Runbook và release record. |

Ghi nhận **sự kiện cụ thể**, không chỉ cảm giác. Ví dụ “test chậm” có thể được làm rõ thành “unit suite của module mất 8 phút, integration suite mất 24 phút, trong khi lỗi format chỉ được báo ở phút 25”.

Không cần thu thập mọi hoạt động của developer hoặc theo dõi cá nhân. Mục tiêu là hiểu **ma sát của hệ thống và quy trình**, không đánh giá năng suất từng người bằng dữ liệu giám sát thiếu bối cảnh.

## 12. Từ tín hiệu đến giả thuyết cải thiện

Một tín hiệu không tự nói cho ta giải pháp. Hãy viết giả thuyết có thể kiểm tra:

~~~text
Quan sát:
Mỗi lần đổi phí giao hàng, developer phải sửa nhiều phương thức.

Giả thuyết:
Các phương thức đang sao chép cùng một chính sách vì chưa có nơi sở hữu chung.

Bằng chứng cần tìm:
- Caller thực sự dùng cùng quy tắc không?
- Các bản sao có khác nhau theo thị trường hoặc kênh không?
- Lịch sử thay đổi có lỗi bỏ sót không?

Hành động dự kiến:
Nếu cùng một hợp đồng, tập trung phép tính tại policy chung và bổ sung test cho caller.

Kết quả mong đợi:
Một thay đổi chính sách chỉ cần cập nhật nơi sở hữu quy tắc;
các luồng liên quan được kiểm chứng bằng test.
~~~

Nếu điều tra cho thấy hai thị trường có chính sách độc lập, giả thuyết “cần gom chung” có thể sai. Khi đó, giải pháp tốt hơn có thể là đặt tên rõ cho từng policy và tài liệu hóa owner.

**Đừng chuyển thẳng từ symptom sang giải pháp quen thuộc.** Một incident timeout không tự động có nghĩa cần tăng timeout; có thể nguyên nhân là query chậm, pool cạn, retry lặp hoặc dependency mất kết nối.

## 13. Ưu tiên hành động cải thiện

Backlog sau incident có thể nhanh chóng quá lớn. Hãy ưu tiên theo tác động và khả năng giảm rủi ro:

| Tiêu chí | Câu hỏi |
| --- | --- |
| **Mức ảnh hưởng** | Có bao nhiêu người dùng, giao dịch hoặc dữ liệu bị ảnh hưởng? |
| **Mức nghiêm trọng** | Có mất dữ liệu, mất tiền, lộ thông tin, vi phạm hợp đồng hoặc downtime không? |
| **Khả năng tái diễn** | Điều kiện kích hoạt còn tồn tại và có thể xuất hiện thường xuyên không? |
| **Phạm vi ảnh hưởng** | Một endpoint hay nhiều service/caller cùng bị ảnh hưởng? |
| **Khả năng phát hiện** | Nhóm có phát hiện nhanh không, hay chỉ biết qua khách hàng? |
| **Chi phí phục hồi** | Mất bao lâu để điều tra, rollback và khôi phục? |
| **Chi phí hành động** | Có thể triển khai nhỏ và an toàn không? |
| **Tính đòn bẩy** | Một cải thiện có ngăn được nhiều loại sự cố tương tự không? |

Một cách phân loại định tính:

- **Ưu tiên khẩn:** rủi ro hiện tại cao, có thể gây tác động nghiêm trọng hoặc đang tiếp diễn.
- **Ưu tiên cao:** sự cố lặp lại hoặc lỗ hổng kiểm soát có phạm vi rộng.
- **Ưu tiên theo kế hoạch:** ma sát lặp lại làm chậm thay đổi hoặc tăng lỗi nhưng chưa tạo nguy cơ khẩn cấp.
- **Cải thiện khi chạm tới:** lợi ích nhỏ, phạm vi hẹp, không có rủi ro đáng kể nếu trì hoãn.

Không nên cộng các tiêu chí thành một điểm số giả chính xác nếu dữ liệu không đủ. Có thể dùng ma trận để hỗ trợ thảo luận, nhưng **owner và nhóm chịu trách nhiệm vẫn phải xem bối cảnh**.

## 14. Không chỉ tạo action item về code

Sau một incident, nhóm có thể cần nhiều loại cải thiện:

| Lớp | Hành động có thể thực hiện | Bằng chứng hoàn tất |
| --- | --- | --- |
| **Code** | Thêm idempotency, xử lý lỗi hoặc transaction boundary. | Test và review hợp đồng. |
| **Test** | Thêm test redelivery, timeout, biên và concurrency. | Test tái hiện tình huống trước đây. |
| **Observability** | Thêm metric duplicate, trace ID hoặc alert. | Dashboard/alert được kiểm chứng bằng tình huống thử. |
| **Architecture** | Làm rõ nơi sở hữu policy hoặc cách giao tiếp giữa service. | Sơ đồ dependency, contract và caller được cập nhật. |
| **Documentation** | Cập nhật runbook, API docs hoặc hướng dẫn khôi phục. | Người khác thực hiện theo tài liệu được. |
| **Deployment** | Thêm canary, rollback hoặc kiểm tra migration. | Diễn tập release/rollback đạt. |
| **Process** | Điều chỉnh review owner, release checklist hoặc escalation. | Quy trình mới được áp dụng và kiểm tra. |
| **Training/knowledge sharing** | Chia sẻ cách đọc trace hoặc phục hồi dữ liệu. | Thành viên khác tự thực hiện được bài tập/diễn tập. |

Không phải sự cố nào cũng cần sửa kiến trúc. Có lúc vấn đề là một cấu hình sai; có lúc cần cập nhật runbook; có lúc chỉ cần bổ sung test. Hành động phải **giải quyết điều kiện góp phần đã xác định**, không phải tạo thêm công việc để báo cáo.

## 15. Thiết kế hành động để tránh tái diễn

Một action item nên viết theo cấu trúc:

- **Động từ cụ thể:** thêm, giới hạn, kiểm tra, tách, đo, diễn tập.
- **Đối tượng rõ:** consumer nào, test nào, dashboard nào, runbook nào.
- **Kết quả có thể xác minh:** điều gì phải đúng sau khi hoàn thành.
- **Owner:** nhóm hoặc người chịu trách nhiệm.
- **Thời hạn:** phù hợp với mức rủi ro.
- **Liên kết:** incident, ticket hoặc PR tạo ra hành động.

Ví dụ kém:

> Cải thiện xử lý message.

Ví dụ tốt hơn:

> Bổ sung cơ chế deduplication theo event ID cho OrderConfirmationHandler; kiểm thử cùng event được giao lại và hai consumer xử lý đồng thời; xác minh gateway nhận cùng idempotency key; owner là nhóm Order Platform; hoàn tất trước đợt mở rộng consumer tiếp theo.

Ví dụ tốt giúp reviewer hiểu **điều kiện hoàn tất**. Nhưng nếu gateway không hỗ trợ idempotency, cần làm rõ lựa chọn kỹ thuật trước khi cam kết ngày hoàn thành.

## 16. Cải thiện khả năng phát hiện và điều tra

Không thể ngăn mọi lỗi. Một hệ thống đáng tin cậy còn cần **phát hiện, khoanh vùng và phục hồi** nhanh khi lỗi xuất hiện.

Những cải thiện thường có ích:

- Correlation ID xuyên qua các service.
- Log có event ID, order ID đã được che/kiểm soát và trạng thái xử lý.
- Metric tỷ lệ retry, duplicate, timeout và backlog.
- Trace cho đường request quan trọng.
- Dashboard có phân loại theo endpoint, tenant hoặc dependency trong giới hạn quyền riêng tư.
- Alert có ngưỡng, owner và runbook.
- Log không ghi secret, token hoặc payload nhạy cảm.
- Synthetic check cho luồng người dùng cốt lõi.

### Tránh “thêm log” mà không có câu hỏi

Một log hữu ích trả lời điều tra cụ thể:

- Event này đã được nhận chưa?
- Đang ở trạng thái nào?
- Có retry bao nhiêu lần?
- Phụ thuộc nào bị timeout?
- Event có cùng ID với lần xử lý trước không?

Nếu log chỉ thêm một câu “processing event” mà không có correlation hoặc trạng thái, nó có thể tăng dung lượng nhưng không giảm thời gian điều tra.

## 17. Dùng khó khăn kiểm thử để cải thiện thiết kế

Test khó viết là một tín hiệu quan trọng, nhưng không phải lúc nào cũng có nghĩa code cần thêm interface.

Hãy xem nguyên nhân:

| Khó khăn | Nguyên nhân có thể | Cải thiện có thể phù hợp |
| --- | --- | --- |
| Không thể test logic nếu không kết nối mạng | Logic nghiệp vụ gọi trực tiếp HTTP client. | Tách logic thuần và ranh giới gateway. |
| Test phụ thuộc thứ tự chạy | Chia sẻ static state hoặc dữ liệu chung. | Cô lập fixture, loại bỏ state toàn cục. |
| Test phải chờ thời gian thực | Dùng clock hệ thống trực tiếp. | Tiêm Clock hoặc ranh giới thời gian phù hợp. |
| Test chập chờn | Race, timeout hoặc phụ thuộc ngoài. | Đồng bộ có kiểm soát, fake dependency hoặc integration environment ổn định. |
| Không biết expected | Đặc tả chưa rõ hoặc nhiều owner. | Làm rõ hợp đồng trước khi viết assertion. |
| Một test cần rất nhiều setup | Nhiều trách nhiệm bị ghép vào một đường gọi. | Xem lại ranh giới module và fixture; chỉ tách khi có lợi ích thật. |

Ví dụ, tiêm java.time.Clock có thể giúp kiểm tra logic hết hạn mà không phải chờ đồng hồ thật:

~~~java
import java.time.Clock;
import java.time.Instant;

public final class ExpirationPolicy {
    private final Clock clock;

    public ExpirationPolicy(Clock clock) {
        this.clock = clock;
    }

    public boolean isExpired(Instant expiresAt) {
        return !clock.instant().isBefore(expiresAt);
    }
}
~~~

JUnit 5 có thể dùng Clock cố định:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

class ExpirationPolicyTest {
    private final Instant fixedNow =
            Instant.parse("2026-11-16T10:00:00Z");

    private final ExpirationPolicy policy =
            new ExpirationPolicy(
                    Clock.fixed(fixedNow, ZoneOffset.UTC));

    @Test
    void expiresAtCurrentInstantIsExpired() {
        assertTrue(policy.isExpired(fixedNow));
    }

    @Test
    void futureExpirationIsNotExpired() {
        assertFalse(policy.isExpired(
                Instant.parse("2026-11-16T10:00:01Z")));
    }
}
~~~

Đây là cải thiện có mục tiêu nếu logic thực sự phụ thuộc thời gian. Không nên tiêm Clock vào mọi lớp chỉ vì có thể; hãy tạo seam ở nơi thời gian là một đầu vào quan trọng.

## 18. Theo dõi hành động đến khi có kết quả

Một postmortem không kết thúc khi tài liệu được viết. Cần theo dõi action item:

~~~mermaid
flowchart TD
    A["Sự cố hoặc ma sát được ghi nhận"] --> B["Thu thập bằng chứng và phân tích điều kiện"]
    B --> C["Đề xuất hành động cụ thể"]
    C --> D["Owner, ưu tiên và tiêu chí hoàn tất"]
    D --> E["Thực hiện code/test/process/observability"]
    E --> F["Kiểm chứng trong test hoặc diễn tập"]
    F --> G{"Rủi ro/ma sát đã giảm?"}
    G -- "Chưa" --> H["Điều chỉnh giả thuyết hoặc hành động"]
    H --> E
    G -- "Có" --> I["Cập nhật tài liệu và đóng action"]
    I --> J["Theo dõi xu hướng tái diễn"]
~~~

Một action có trạng thái “Done” chỉ vì PR đã merge là chưa đủ. Cần xác minh **kết quả mong đợi đã xuất hiện**.

Ví dụ:

- PR thêm metric duplicate đã merge, nhưng dashboard không hiển thị metric ở production.
- Runbook đã cập nhật, nhưng người trực khác vẫn không thể làm theo.
- Test redelivery đã thêm, nhưng chỉ kiểm tra hai lần gọi cùng một object trong cùng process, không kiểm tra persistence sau restart.
- Cơ chế retry đã đổi, nhưng tỷ lệ message bị mất hoặc xử lý trùng chưa được quan sát.

Theo dõi sau triển khai giúp xác nhận cải thiện có tác dụng trong điều kiện thật.

## 19. Đo xem nhóm có học được từ sự cố không

Không nên dùng số lượng postmortem hoặc số action item đã đóng làm thước đo duy nhất. Một báo cáo dài và nhiều task chưa chắc cải thiện hệ thống.

Các tín hiệu có thể theo dõi:

| Tín hiệu | Ý nghĩa | Cần diễn giải cùng |
| --- | --- | --- |
| **Incident recurrence** | Cùng dạng sự cố có lặp lại không? | Mức thay đổi tải, feature và cách phân loại incident. |
| **Time to detect (TTD)** | Mất bao lâu để phát hiện vấn đề? | Thời điểm sự cố thực sự bắt đầu và độ phủ monitoring. |
| **Time to mitigate/recover** | Mất bao lâu để giảm tác động và phục hồi? | Mức độ nghiêm trọng và khả năng rollback. |
| **Mean time to restore (MTTR)** | Xu hướng thời gian phục hồi của dịch vụ. | Phân phối sự cố, mức độ và cách định nghĩa thời điểm kết thúc. |
| **Duplicate/lost processing rate** | Có bao nhiêu event bị xử lý lặp hoặc mất? | Volume event và semantics của broker/provider. |
| **Flaky test rate** | Độ tin cậy của feedback tự động. | Số lần chạy, môi trường và loại test. |
| **Time to first useful test feedback** | Developer chờ bao lâu để biết thay đổi có vấn đề? | Queue time và stage execution time. |
| **Manual recovery steps** | Mức phụ thuộc thao tác thủ công. | Độ phức tạp và quyền cần thiết. |
| **Time to find ownership** | Mất bao lâu để xác định ai có thể giúp? | Cấu trúc nhóm và mức độ thay đổi tổ chức. |

Các metric này không phải bảng xếp hạng cá nhân. Nếu nhóm dùng MTTR để phạt người trực, họ có thể tránh ghi nhận sự cố hoặc chọn thời điểm đóng incident có lợi. Mục đích là tìm **xu hướng hệ thống** và xác định cải thiện nào có ích.

Không kỳ vọng mọi chỉ số đều giảm sau một lần thay đổi. Ví dụ, monitoring tốt hơn có thể làm số incident được phát hiện tăng lên vì trước đây chúng bị bỏ sót.

## 20. Chia sẻ bài học để tránh lặp lại ở nhóm khác

Một sự cố tại một service có thể tiết lộ rủi ro ở nhiều service dùng cùng thư viện hoặc quy trình.

Sau khi xác định điều kiện góp phần, hãy hỏi:

- Có service khác dùng cùng consumer pattern không?
- Có nhiều module tự triển khai retry/idempotency khác nhau không?
- Có cùng template CI bỏ qua một loại test không?
- Runbook ở nhóm khác có cùng điểm mơ hồ không?
- Một thư viện dùng chung có cần thêm guardrail không?
- Có thể tạo một ví dụ hoặc guideline để các nhóm áp dụng không?

Không nên phát động một chiến dịch refactor toàn hệ thống chỉ vì một incident. Trước hết, tìm **phạm vi có cùng điều kiện rủi ro** và xác nhận nơi nào thực sự bị ảnh hưởng.

Chia sẻ bài học cần đủ cụ thể để nhóm khác tự đánh giá:

- Điều kiện gây sự cố là gì?
- Dấu hiệu nhận biết ở service khác?
- Kiểm tra hoặc test nào có thể phát hiện?
- Ai có thể hỗ trợ xác nhận?
- Có một mẫu triển khai hoặc guardrail dùng chung nào phù hợp không?

## 21. Tránh các phản ứng làm tăng ma sát

Một số phản ứng sau sự cố có vẻ quyết liệt nhưng có thể làm hệ thống tệ hơn:

| Phản ứng thiếu cân nhắc | Rủi ro | Hướng tốt hơn |
| --- | --- | --- |
| Thêm nhiều bước phê duyệt cho mọi thay đổi | Tăng thời gian nhưng không chắc giảm rủi ro. | Áp dụng review/gate theo vùng và mức rủi ro. |
| Tắt retry để tránh message lặp | Có thể làm mất khả năng phục hồi khi lỗi tạm thời. | Giữ retry có kiểm soát và xử lý idempotent. |
| Tăng timeout cho mọi request | Giữ connection lâu hơn và che nguyên nhân chậm. | Đo dependency, timeout budget và retry behavior. |
| Thêm log toàn bộ payload | Rò rỉ dữ liệu và tăng chi phí lưu trữ. | Log ID, trạng thái và trường đã được kiểm soát. |
| Viết lại service ngay sau incident | Tăng rủi ro khi chưa hiểu nguyên nhân. | Tạo thay đổi nhỏ, kiểm chứng từng giả thuyết. |
| Bắt buộc thêm test cho mọi dòng | Test hình thức, suite chậm và khó bảo trì. | Test hợp đồng, nhánh rủi ro và lỗi đã gặp. |
| Ghi action “developer phải cẩn thận” | Không tạo guardrail hay cơ chế phát hiện. | Cải thiện công cụ, quy trình, test hoặc tài liệu. |
| Đóng incident ngay khi dashboard xanh | Backlog hoặc dữ liệu sai có thể còn tồn tại. | Xác minh phục hồi và hậu quả còn lại. |

Mục tiêu không phải thêm càng nhiều kiểm soát càng tốt. Mục tiêu là **đặt kiểm soát đúng chỗ, có tác dụng và không tạo gánh nặng vượt quá rủi ro được giảm**.

## 22. Mẫu maintenance learning review cho khó khăn lặp lại

Không phải ma sát bảo trì nào cũng cần một postmortem đầy đủ. Với vấn đề nhỏ nhưng lặp lại, có thể dùng một bản ghi ngắn:

~~~markdown
# Maintenance learning: test checkout mất nhiều thời gian

## Quan sát
Một thay đổi nhỏ trong ShippingFeePolicy phải chờ toàn bộ integration stack
khởi động trước khi test logic cơ bản.

## Bằng chứng
- Unit test hiện chưa tách khỏi service khởi tạo database.
- Thời gian chờ trung vị của job test logic là 7 phút.
- Nhiều lần sửa chỉ thay đổi quy tắc tính phí thuần.

## Tác động
- Feedback chậm.
- Developer phải rerun nhiều bước không liên quan.
- Khó xác định test nào thực sự bảo vệ quy tắc phí.

## Giả thuyết
Logic tính phí có thể được kiểm tra độc lập tại một ranh giới thuần,
trong khi integration test vẫn bảo vệ việc wiring và caller.

## Hành động
- Bổ sung unit test cho chính sách phí.
- Giữ integration test cho đường checkout.
- Đo lại thời gian feedback sau thay đổi.

## Owner / tiêu chí hoàn tất
- Owner: nhóm Checkout.
- Unit test chạy không cần database.
- Integration test vẫn xác minh đường gọi thật.
- Báo cáo thời gian trước/sau trong cùng môi trường.
~~~

Mẫu này giúp biến một phàn nàn “test chậm” thành giả thuyết và tiêu chí kiểm chứng.

## 23. Vai trò và trách nhiệm khi học từ sự cố

Việc cải thiện cần sự phối hợp giữa nhiều vai trò:

| Vai trò | Trách nhiệm phù hợp |
| --- | --- |
| **Người phát hiện/on-call** | Ghi nhận tác động, timeline, bằng chứng và hành động giảm thiểu. |
| **Incident lead** | Điều phối xử lý, cập nhật trạng thái và bảo đảm ưu tiên khôi phục. |
| **Service owner** | Giải thích hợp đồng, phụ thuộc và quyết định kỹ thuật của service. |
| **Developer** | Phân tích code path, test, sửa lỗi và triển khai cải thiện. |
| **QA/test engineer** | Xác định lỗ hổng kiểm thử và bổ sung kịch bản phù hợp. |
| **Platform/SRE** | Cải thiện deploy, monitoring, capacity, recovery và guardrail dùng chung. |
| **Product/business owner** | Xác nhận tác động, quy tắc nghiệp vụ và mức chấp nhận rủi ro. |
| **Engineering manager/lead** | Bảo đảm owner, ưu tiên và thời gian cho các hành động liên nhóm. |

Một người có thể đảm nhiệm nhiều vai trò ở nhóm nhỏ. Điều quan trọng là **quyền quyết định và trách nhiệm được làm rõ**, tránh action item bị bỏ ngỏ vì ai cũng nghĩ nhóm khác sẽ làm.

Không cần mời tất cả mọi người vào mọi cuộc họp. Mời những người có bằng chứng, hiểu hệ thống hoặc sở hữu hành động; chia sẻ kết quả cho các nhóm liên quan.

## 24. Khi nào cần nâng cấp vấn đề thay vì xử lý trong nhóm?

Một số phát hiện vượt quá quyền quyết định của service team:

- Lỗ hổng ảnh hưởng nhiều sản phẩm hoặc cần quyết định security.
- Dữ liệu có nguy cơ vi phạm quy định hoặc cần quy trình response riêng.
- Nền tảng chung gây lỗi ở nhiều nhóm.
- Một dependency vendor có rủi ro hỗ trợ hoặc licensing.
- Sự cố có tác động khách hàng lớn và cần thông báo theo quy trình.
- Cần thay đổi SLO, capacity hoặc ngân sách vận hành.

Khi ấy, nhóm cần **escalate tới owner phù hợp**, cung cấp bằng chứng và đề xuất hành động. Không nên tự ý thay policy bảo mật, xóa dữ liệu hoặc thay đổi cam kết với khách hàng chỉ để đóng action item.

Việc escalation cũng cần có owner và trạng thái theo dõi. Chuyển ticket sang nhóm khác mà không xác nhận họ đã nhận trách nhiệm chưa phải là giải quyết vấn đề.

## 25. Checklist sau một sự cố hoặc khi phát hiện ma sát

- **Tác động đã được mô tả bằng dữ liệu nào?**
- **Timeline có nguồn bằng chứng và phân biệt sự kiện với giả thuyết không?**
- **Triệu chứng, nguyên nhân gần và điều kiện góp phần đã được tách chưa?**
- **Phân tích tập trung vào hệ thống và guardrail, không đổ lỗi cá nhân không?**
- **Hành động giảm thiểu, khắc phục, phòng ngừa, phát hiện và phục hồi đã được phân biệt chưa?**
- **Có hành động cụ thể cho code, test, observability, tài liệu hoặc quy trình không?**
- **Mỗi action có owner, thời hạn và tiêu chí hoàn tất không?**
- **Hành động có xử lý nguyên nhân/điều kiện góp phần thay vì chỉ triệu chứng không?**
- **Có kiểm thử hoặc diễn tập để xác minh hành động không?**
- **Có nhóm khác dùng cùng pattern cần được thông báo không?**
- **Dữ liệu nhạy cảm được bảo vệ trong báo cáo và log không?**
- **Sau triển khai có đo xem rủi ro hoặc ma sát đã giảm không?**

## 26. Bài tập tự luyện

### Tình huống A — Message bị giao lại

Một consumer nhận cùng event ba lần sau khi broker mất kết nối. Nhóm tăng thời gian acknowledgment timeout và sự cố giảm trong vài ngày.

**Câu hỏi:** Nhóm đã giải quyết nguyên nhân chưa? Cần điều tra điều gì?

**Gợi ý:** Tăng timeout có thể giảm xác suất redelivery nhưng chưa bảo đảm xử lý idempotent. Kiểm tra thời điểm side effect, acknowledgment, event ID, retry, crash window và khả năng provider deduplicate.

### Tình huống B — Chỉ có một người biết rollback

Mỗi lần phát hành database migration, một developer phải trực tiếp chạy script phục hồi vì runbook không đầy đủ.

**Câu hỏi:** Đây có phải khó khăn bảo trì dù chưa từng xảy ra outage?

**Gợi ý:** Có. Quy trình phụ thuộc một cá nhân và khó phục hồi khi người đó vắng mặt. Cần tài liệu, quyền phù hợp và diễn tập để người khác thực hiện an toàn.

### Tình huống C — Log quá nhiều nhưng vẫn khó tìm lỗi

Nhóm thêm log toàn bộ request body. Khi sự cố xảy ra, log tăng mạnh, có dữ liệu nhạy cảm và không thể nối request qua service.

**Câu hỏi:** Cải thiện nào phù hợp hơn?

**Gợi ý:** Dùng correlation/trace ID, log trạng thái và trường được kiểm soát, che dữ liệu nhạy cảm và thiết kế truy vấn theo câu hỏi điều tra.

### Tình huống D — Test flaky được retry đến khi xanh

Một integration test thất bại 20% số lần chạy. Nhóm cấu hình retry 5 lần và đánh dấu pipeline xanh nếu một lần pass.

**Câu hỏi:** Vì sao đây chưa phải giải pháp hoàn chỉnh?

**Gợi ý:** Retry che khuất độ không ổn định và làm mất tín hiệu. Cần xác định nguyên nhân, đo flaky rate, cô lập dữ liệu và có owner/thời hạn cho quarantine nếu cần.

### Tình huống E — Incident do quy tắc sao chép

Hai service cùng tính phí. Một service cập nhật ngưỡng miễn phí nhưng service kia chưa cập nhật, dẫn tới khách hàng bị thu sai.

**Câu hỏi:** Ngoài sửa con số sai, nhóm nên học điều gì?

**Gợi ý:** Xác nhận hai service có cùng hợp đồng không; nếu có, thiết lập nơi sở hữu policy, test contract cho caller và tìm các bản sao khác. Nếu hai chính sách độc lập, tài liệu hóa sự khác biệt thay vì hợp nhất máy móc.

### Tình huống F — Không có alert nhưng người dùng báo lỗi

Một endpoint trả lỗi 2% trong 40 phút nhưng alert chỉ kích hoạt khi tỷ lệ lỗi vượt 10%.

**Câu hỏi:** Có thể kết luận alert sai chỉ từ con số 2% không?

**Gợi ý:** Cần xem SLO, baseline, volume, endpoint quan trọng và mức tác động. Tinh chỉnh alert theo mục tiêu người dùng và tín hiệu đủ tin cậy; không đặt ngưỡng chỉ để giảm số trang báo.

### Tình huống G — Action item không có owner

Postmortem ghi “cải thiện observability”, “viết thêm test” và “tối ưu retry” nhưng không có người phụ trách hoặc tiêu chí hoàn tất.

**Câu hỏi:** Điều gì có khả năng xảy ra?

**Gợi ý:** Các việc dễ bị quên hoặc đóng hình thức. Chuyển thành hành động cụ thể, owner, hạn, bằng chứng và bước follow-up.

### Tình huống H — Chỉ sửa code sau incident

Một lỗi do migration không tương thích được xử lý bằng cách sửa query. Nhóm không kiểm tra quy trình rollout, backward compatibility hoặc rollback.

**Câu hỏi:** Những lớp nào có thể còn rủi ro?

**Gợi ý:** Schema migration, phiên bản service chạy đồng thời, dữ liệu cũ/mới, deployment ordering và recovery. Cần kiểm thử migration/rollout theo tình huống triển khai thực tế.

---

**Ghi nhớ:** Sự cố và khó khăn bảo trì là nguồn bằng chứng để cải thiện hệ thống. Hãy ghi nhận tác động và timeline, phân biệt triệu chứng với các điều kiện góp phần, phân tích theo cách không đổ lỗi, rồi chuyển bài học thành hành động cụ thể trong code, test, observability, tài liệu hoặc quy trình. Mỗi hành động cần **owner, tiêu chí hoàn tất và bước kiểm chứng sau triển khai**. Mục tiêu không phải chỉ đóng incident hay đóng ticket, mà là giảm khả năng tái diễn, rút ngắn thời gian phát hiện và phục hồi, đồng thời làm những thay đổi tiếp theo dễ hiểu và an toàn hơn.
