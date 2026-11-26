# Resubmission

*Gửi lại các event publication chưa hoàn tất trong Spring Modulith*

Trong một ứng dụng chia thành nhiều module, publisher thường phát application event trong transaction nghiệp vụ, còn listener xử lý sau khi transaction đó commit. Cách tổ chức này giúp module phát sự kiện không phải gọi trực tiếp module nhận. Tuy vậy, listener vẫn có thể thất bại vì dịch vụ bên ngoài tạm ngừng, kết nối cơ sở dữ liệu bị gián đoạn hoặc tiến trình ứng dụng dừng giữa chừng.

Spring Modulith cung cấp **event publication registry** để theo dõi việc giao từng event đến từng transactional listener. Khi một publication chưa được đánh dấu hoàn tất, ứng dụng có thể **resubmit** publication đó để listener xử lý lại. Cơ chế này giúp khôi phục việc giao sự kiện đáng tin cậy sau lỗi, nhưng mỗi lần gửi lại vẫn có thể chạy listener nhiều hơn một lần. Vì vậy, listener phải được thiết kế idempotent và quy trình retry cần có giới hạn, quan sát được.

## 1. Phân biệt event chưa được phát và publication chưa hoàn tất

Hai tình huống này cần cách xử lý khác nhau:

| Tình huống | Điều đã xảy ra | Cách xử lý phù hợp |
|---|---|---|
| Transaction của publisher rollback | Thay đổi nghiệp vụ và việc phát event chưa commit | Điều tra transaction gốc; không có publication đã commit để resubmit |
| Event đã commit, listener xử lý thất bại | Registry còn publication chưa hoàn tất cho listener đó | Khắc phục nguyên nhân rồi resubmit publication |
| Listener đã xử lý xong nhưng ứng dụng dừng trước khi ghi nhận hoàn tất | Tác động nghiệp vụ có thể đã xảy ra, trạng thái publication vẫn chưa hoàn tất | Resubmit an toàn nhờ idempotency và khóa chống trùng |
| Payload không còn tương thích hoặc dữ liệu event bị lỗi | Listener không thể xử lý event ngay cả khi được gọi lại | Sửa tương thích dữ liệu hoặc xử lý thủ công theo quy trình nghiệp vụ |

Resubmission chỉ giải quyết việc giao lại một publication đã được registry ghi nhận. Nó không tạo lại event đã mất trước commit, không rollback transaction publisher và cũng không tự sửa dữ liệu nghiệp vụ sai.

## 2. Registry theo dõi từng listener như thế nào?

Với transactional event listener được Spring Modulith quản lý, registry ghi nhận publication cho từng listener nhận event. Một event có ba listener có thể tạo ra ba publication riêng. Do đó, hai listener hoàn tất và một listener thất bại sẽ có trạng thái riêng; khi khôi phục, chỉ publication chưa hoàn tất cần được gửi lại.

Luồng xử lý thường diễn ra như sau:

1. Publisher phát event trong transaction nghiệp vụ.
2. Registry ghi nhận publication cho các transactional listener liên quan trong cùng ranh giới transaction.
3. Khi transaction commit, listener được gọi theo cấu hình của nó. `@ApplicationModuleListener` là lựa chọn thường dùng trong Spring Modulith cho listener chạy bất đồng bộ và trong transaction riêng sau commit.
4. Khi listener xử lý thành công, registry đánh dấu publication tương ứng đã hoàn tất.
5. Nếu listener ném exception hoặc tiến trình dừng trước khi trạng thái hoàn tất được lưu, publication vẫn được xem là chưa hoàn tất và có thể được tìm để resubmit.

Trạng thái hoàn tất gắn với từng cặp event và listener, không phải một cờ duy nhất cho toàn bộ event. Điều này cho phép khôi phục một nhánh giao sự kiện bị lỗi mà không cần phát lại các nhánh đã hoàn thành.

Ví dụ, module đơn hàng phát `OrderPlaced`. Module kho xử lý thành công, nhưng module thông báo gặp lỗi kết nối email. Registry có thể giữ publication của listener thông báo ở trạng thái chưa hoàn tất. Sau khi dịch vụ email hoạt động lại, ứng dụng resubmit publication đó; listener kho không cần chạy lại chỉ vì listener thông báo đã thất bại.

## 3. Resubmit publication bằng Spring Modulith

Spring Modulith cung cấp `IncompleteEventPublications` để tìm và resubmit các publication chưa hoàn tất. Có thể giới hạn việc gửi lại theo loại event hoặc điều kiện phù hợp với quy trình vận hành.

Giả sử ứng dụng có event bất biến sau:

```java
import java.time.Instant;
import java.util.UUID;

public record PaymentCaptured(
    UUID eventId,
    UUID orderId,
    Instant occurredAt
) {}
```

Listener xử lý event có thể được khai báo như sau:

```java
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class PaymentProjectionListener {

    private final PaymentProjection projection;

    PaymentProjectionListener(PaymentProjection projection) {
        this.projection = projection;
    }

    @ApplicationModuleListener
    void on(PaymentCaptured event) {
        projection.apply(event);
    }
}
```

Một thành phần phục hồi có thể gửi lại các publication của `PaymentCaptured`:

```java
import org.springframework.modulith.events.IncompleteEventPublications;
import org.springframework.stereotype.Component;

@Component
class PaymentPublicationRecovery {

    private final IncompleteEventPublications incompletePublications;

    PaymentPublicationRecovery(
            IncompleteEventPublications incompletePublications) {
        this.incompletePublications = incompletePublications;
    }

    void resubmitPaymentEvents() {
        incompletePublications.resubmitIncompletePublications(
            publication -> publication.getEvent() instanceof PaymentCaptured
        );
    }
}
```

Đoạn mã minh họa cách chọn publication theo loại event. Trong ứng dụng thực tế, chỉ gọi thao tác này sau khi đã kiểm tra nguyên nhân lỗi và xác định phạm vi cần khôi phục. API cụ thể và cấu hình lưu publication phụ thuộc phiên bản Spring Modulith cùng module lưu trữ mà ứng dụng sử dụng; hãy đối chiếu dependency đang triển khai trước khi tích hợp.

Không nên tạo một event mới bằng cách gọi publisher lần nữa chỉ để thay thế resubmission. Event mới có danh tính và vòng đời publication mới, có thể kích hoạt tất cả listener và tạo tác động nghiệp vụ trùng lặp. Resubmit sử dụng publication chưa hoàn tất mà registry đã theo dõi.

## 4. Thiết kế retry có kiểm soát

Registry cung cấp dữ liệu về publication chưa hoàn tất và cơ chế gửi lại. Chính sách retry của ứng dụng cần quyết định thời điểm, số lần, phạm vi và cách xử lý lỗi kéo dài.

**Phân loại lỗi trước khi retry.** Timeout, lỗi mạng hoặc dịch vụ phụ thuộc tạm ngừng thường có thể thử lại. Event không hợp lệ, vi phạm quy tắc nghiệp vụ hoặc payload không tương thích cần được điều tra và sửa nguyên nhân trước. Gửi lại liên tục một event lỗi vĩnh viễn chỉ làm tăng tải và gây nhiễu log.

**Dùng backoff và giới hạn lần thử.** Với lỗi tạm thời, có thể tăng dần khoảng chờ giữa các lần thử, thêm jitter để nhiều instance không đồng loạt gọi lại dịch vụ, và đặt giới hạn số lần tự động. Khi vượt giới hạn, giữ publication để người vận hành điều tra và quyết định bước tiếp theo. Registry không thay thế chính sách phân loại lỗi, backoff hay quy trình xử lý thủ công của ứng dụng.

**Chọn đúng phạm vi.** Lọc theo loại event, listener hoặc điều kiện nghiệp vụ cần thiết; xử lý theo batch nếu số lượng lớn. Tránh resubmit toàn bộ publication chưa hoàn tất trong một thao tác không giới hạn. Với nhiều instance ứng dụng, cần phối hợp lịch retry hoặc cơ chế khóa phù hợp để tránh nhiều instance cùng khởi chạy một đợt phục hồi.

**Giữ exception có ý nghĩa.** Nếu listener bắt exception rồi bỏ qua, framework có thể xem lần gọi đó là thành công và publication được đánh dấu hoàn tất. Chỉ bắt lỗi khi listener thực sự xử lý được hoặc chuyển lỗi sang một trạng thái được theo dõi rõ ràng; nếu chưa xử lý được, hãy để lỗi truyền ra theo cơ chế transaction của listener.

## 5. Idempotency bảo vệ tác động nghiệp vụ

Resubmission có ngữ nghĩa giao ít nhất một lần trong các tình huống lỗi. Ví dụ, listener đã gọi dịch vụ thanh toán thành công nhưng tiến trình dừng trước khi registry lưu trạng thái hoàn tất. Lần resubmit tiếp theo có thể gọi listener lần nữa. Vì vậy, không được giả định rằng một event chỉ được xử lý đúng một lần.

Một listener idempotent cho cùng kết quả khi nhận lại cùng một event. Có thể triển khai bằng các cách sau:

- Dùng `eventId` ổn định làm khóa idempotency; lưu dấu event đã áp dụng với ràng buộc unique trong cùng transaction cập nhật dữ liệu nghiệp vụ.
- Với thao tác cập nhật trạng thái, kiểm tra trạng thái hiện tại và chỉ chuyển trạng thái khi điều kiện hợp lệ.
- Khi gọi hệ thống bên ngoài, truyền `eventId` làm idempotency key nếu API đích hỗ trợ. Nếu không hỗ trợ, cần thiết kế bảng ghi nhận yêu cầu hoặc quy trình đối soát phù hợp.
- Tránh tạo side effect không thể đảo ngược trước khi xác định cách xử lý trường hợp listener chạy lại.

Ví dụ, thao tác áp dụng projection có thể kiểm tra event đã được ghi nhận:

```java
import org.springframework.transaction.annotation.Transactional;

@Transactional
public void apply(PaymentCaptured event) {
    if (processedEvents.existsById(event.eventId())) {
        return;
    }

    paymentProjection.updateFor(event.orderId());
    processedEvents.save(new ProcessedEvent(event.eventId()));
}
```

Việc cập nhật projection và lưu `ProcessedEvent` phải nằm trong cùng transaction để tránh tình huống một thao tác đã commit nhưng dấu chống trùng chưa được lưu, hoặc ngược lại. Với side effect ở hệ thống bên ngoài, transaction cơ sở dữ liệu cục bộ không thể bảo đảm tính nguyên tử; hãy dùng idempotency key, API có khả năng tra cứu kết quả hoặc quy trình đối soát.

## 6. Quan sát và quy trình vận hành

Một quy trình phục hồi đáng tin cậy cần cho người vận hành biết publication nào đang chờ, chờ bao lâu và listener nào gặp lỗi. Tối thiểu nên theo dõi:

- Số publication chưa hoàn tất, phân nhóm theo loại event và listener.
- Tuổi của publication chưa hoàn tất lâu nhất và số lượng vượt ngưỡng thời gian xử lý.
- Số lần resubmit, tỷ lệ hoàn tất sau retry và các lỗi lặp lại.
- Nguyên nhân lỗi gần nhất, mã tương quan và event ID; tránh ghi payload chứa dữ liệu nhạy cảm vào log.

Khi xử lý sự cố, người vận hành nên xác định listener và event bị ảnh hưởng, đọc nguyên nhân lỗi, khôi phục dependency hoặc sửa dữ liệu cần thiết, xác nhận listener có thể chạy lặp an toàn, rồi resubmit một phạm vi nhỏ. Sau đó kiểm tra trạng thái publication và kết quả nghiệp vụ ở module nhận. Nếu vẫn thất bại, dừng retry tự động theo chính sách và chuyển sang xử lý thủ công.

Không xóa publication chưa hoàn tất chỉ để làm sạch màn hình giám sát. Xóa dấu vết có thể khiến ứng dụng mất khả năng phục hồi hoặc đối soát. Chỉ dọn publication theo chính sách lưu trữ đã xác định, sau khi kết quả nghiệp vụ và yêu cầu kiểm toán cho phép.

## 7. Kiểm thử resubmission

Kiểm thử nên xác nhận cả trạng thái registry lẫn tác động nghiệp vụ. Với cơ sở dữ liệu kiểm thử tương thích với cấu hình lưu publication của ứng dụng, có thể xây dựng các tình huống sau:

1. **Listener thất bại rồi phục hồi:** cho listener ném exception ở lần đầu, xác nhận publication còn chưa hoàn tất, sau đó resubmit và xác nhận publication hoàn tất.
2. **Nhiều listener, một listener lỗi:** xác nhận publication của listener thành công vẫn hoàn tất; resubmit chỉ kích hoạt listener còn lỗi.
3. **Gửi lại cùng event:** resubmit lặp lại một event và xác nhận dữ liệu nghiệp vụ chỉ thay đổi một lần nhờ idempotency.
4. **Publisher rollback:** xác nhận transaction publisher rollback không để lại event đã commit cần phục hồi.
5. **Lỗi kéo dài:** xác nhận chính sách giới hạn retry, cảnh báo và chuyển xử lý thủ công hoạt động như dự kiến.

Không chỉ kiểm tra rằng phương thức resubmit được gọi. Bài kiểm thử cần xác nhận listener thực sự chạy lại, publication chuyển sang trạng thái hoàn tất khi thành công và kết quả nghiệp vụ không bị nhân đôi.

## 8. Những điểm cần nhớ

- Registry theo dõi publication cho từng transactional listener; một event có thể có listener hoàn tất và listener chưa hoàn tất.
- Resubmission gửi lại publication đã tồn tại, không phát một event nghiệp vụ mới.
- Retry cần phân loại lỗi, backoff, giới hạn, lọc phạm vi và quan sát được.
- Listener phải idempotent vì lần gửi lại có thể lặp lại side effect đã xảy ra trước khi trạng thái hoàn tất được ghi nhận.
- Kiểm thử cả vòng đời publication và kết quả nghiệp vụ để chứng minh khả năng phục hồi.

Khi kết hợp publisher và listener theo ranh giới module, xử lý sau commit, publication registry và quy trình resubmission có kiểm soát, Spring Modulith giúp ứng dụng khôi phục việc giao application event sau sự cố mà vẫn giữ được tính nhất quán của nghiệp vụ.
