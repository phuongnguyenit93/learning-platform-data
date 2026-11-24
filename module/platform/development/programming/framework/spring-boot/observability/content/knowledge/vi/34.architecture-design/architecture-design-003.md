# Chọn log cho chi tiết nghiệp vụ

Trong một ứng dụng Spring Boot, metrics cho biết xu hướng, distributed tracing cho thấy một yêu cầu đi qua những thành phần nào, còn log giải thích một sự kiện cụ thể đã xảy ra và vì sao nó xảy ra. Khi điều tra một đơn thuê không được xác nhận, chẳng hạn, ta thường cần biết trạng thái trước và sau xử lý, quyết định nghiệp vụ nào đã được áp dụng, kết quả gọi hệ thống thanh toán và mã lý do của thất bại. Đó là những chi tiết nên được ghi thành log có cấu trúc.

Mục tiêu không phải ghi lại mọi dòng lệnh đã chạy. Mục tiêu là chọn đúng các sự kiện có giá trị điều tra, đặt tên và trường dữ liệu ổn định, rồi liên kết chúng với trace để người trực vận hành có thể đi từ một dấu hiệu bất thường đến đúng lần xử lý.

Sau bài học, bạn có thể:

- Phân biệt vai trò của log với metrics và distributed tracing.
- Chọn các điểm ghi log theo sự kiện và chuyển trạng thái nghiệp vụ.
- Thiết kế log có cấu trúc với tên sự kiện, mã kết quả và ngữ cảnh tương quan.
- Kết hợp log với Micrometer Observation và trace context trong Spring Boot.
- Tránh log trùng lặp, dữ liệu nhạy cảm và nhãn metrics có cardinality cao.

## 1. Log trả lời câu hỏi nào?

Hãy xét luồng xác nhận một đơn thuê. Một yêu cầu đi vào API, tải đơn thuê từ cơ sở dữ liệu, kiểm tra trạng thái, gọi dịch vụ thanh toán và cập nhật đơn. Ba tín hiệu observability trả lời ba nhóm câu hỏi khác nhau:

| Tín hiệu | Câu hỏi chính | Ví dụ |
|---|---|---|
| Metrics | Việc gì đang xảy ra trên diện rộng? | Tỷ lệ xác nhận thành công giảm từ 98% xuống 82%; độ trễ p95 tăng. |
| Distributed tracing | Một lần xử lý đã đi qua đâu và chậm ở đâu? | Span gọi dịch vụ thanh toán chiếm 1,8 giây trong tổng thời gian 2 giây. |
| Logs | Sự kiện cụ thể nào đã xảy ra và có dữ liệu gì để giải thích? | Đơn bị từ chối vì trạng thái hiện tại là `CANCELLED`; cổng thanh toán trả mã `INSUFFICIENT_FUNDS`. |

Một log tốt bổ sung thông tin mà metrics và trace không nên cố gắng mang theo. Metrics cần nhãn có tập giá trị hữu hạn để tổng hợp hiệu quả. Trace thể hiện quan hệ thời gian và phụ thuộc giữa các span. Log có thể mang các trường chi tiết của một sự kiện, chẳng hạn mã đơn thuê hoặc mã lỗi từ hệ thống ngoài, miễn là chính sách dữ liệu và chi phí lưu trữ cho phép.

Không nên biến log thành bản sao của toàn bộ request, response hay trạng thái đối tượng. Dữ liệu quá lớn làm tăng chi phí, khó truy vấn và có thể làm lộ thông tin riêng tư.

## 2. Chọn sự kiện nghiệp vụ đáng ghi log

Hãy bắt đầu từ câu hỏi mà đội vận hành, hỗ trợ hoặc phát triển cần trả lời. Một sự kiện đáng ghi log thường thuộc một trong các nhóm sau.

### 2.1. Chuyển trạng thái có ý nghĩa

Ghi log khi một thực thể nghiệp vụ chuyển qua một trạng thái quan trọng:

- Đơn thuê được tạo, xác nhận, hủy hoặc hoàn tất.
- Khoản thanh toán được chấp nhận, từ chối hoặc hoàn tiền.
- Yêu cầu hoàn tất kiểm tra điều kiện hoặc bị từ chối.

Một sự kiện chuyển trạng thái nên có trạng thái trước và sau, định danh thực thể cần điều tra, kết quả và thời điểm. Nếu cập nhật trạng thái thất bại, log phải mô tả lần thử thất bại thay vì ghi như thể trạng thái đã thay đổi thành công.

### 2.2. Quyết định nghiệp vụ

Ghi log khi hệ thống đưa ra quyết định có thể cần giải thích sau này: chấp nhận hay từ chối một yêu cầu, chọn phương án xử lý dự phòng, áp dụng một quy tắc tính phí hoặc đánh dấu một giao dịch cần kiểm tra thêm.

Hãy ưu tiên mã lý do ổn định như `INVALID_STATE`, `POLICY_NOT_MET` hoặc `PAYMENT_DECLINED`. Mã lý do giúp truy vấn và thống kê nhất quán hơn câu mô tả tự do. Nếu cần thêm diễn giải cho con người, đặt nó trong message.

Không phải mọi quyết định từ chối đều là lỗi kỹ thuật. Một yêu cầu bị từ chối đúng theo quy tắc nghiệp vụ có thể là kết quả bình thường. Chọn log level theo ý nghĩa vận hành, không chỉ theo việc kết quả có phải `success` hay không.

### 2.3. Tương tác với hệ thống bên ngoài

Ghi các kết quả quan trọng tại ranh giới tích hợp: yêu cầu được gửi, phản hồi thành công, phản hồi bị từ chối, timeout hoặc lỗi kết nối. Log nên có tên hệ thống đích, thao tác, kết quả, mã lỗi đã chuẩn hóa và thời gian xử lý nếu cần.

Không ghi toàn bộ payload hoặc header. Thường chỉ cần mã giao dịch do đối tác cấp, mã kết quả và một số trường đã được cho phép. Bí mật xác thực, token, dữ liệu thẻ và thông tin cá nhân không được đưa vào log.

### 2.4. Lỗi và đường xử lý bất thường

Ghi log khi ứng dụng cần điều tra hoặc hành động: lỗi không mong đợi, timeout, dữ liệu không nhất quán, retry cạn số lần hoặc fallback được kích hoạt. Log cần cho biết thao tác nào thất bại, loại lỗi, mã lỗi, định danh tương quan và liệu hệ thống có tiếp tục được hay không.

Tránh ghi cùng một exception ở mọi tầng. Một exception được log ở tầng repository, service, controller và bộ xử lý toàn cục sẽ tạo nhiều bản ghi giống nhau mà không bổ sung ngữ cảnh. Hãy chọn tầng thực sự xử lý hoặc chuyển exception thành kết quả nghiệp vụ để ghi một lần với thông tin đầy đủ nhất.

## 3. Thiết kế một bản ghi log có cấu trúc

Log có cấu trúc lưu dữ liệu theo các trường riêng biệt thay vì ghép mọi thứ thành một câu văn. Backend có thể lập chỉ mục, lọc và tổng hợp từng trường mà không cần phân tích lại message.

Một sự kiện xác nhận đơn thuê có thể có dạng minh họa sau:

```json
{
  "timestamp": "2026-11-22T07:15:30.412Z",
  "level": "INFO",
  "service.name": "rental-api",
  "event.name": "rental.booking.confirmed",
  "event.version": 1,
  "booking.id": "bkg_7f31",
  "state.from": "PENDING",
  "state.to": "CONFIRMED",
  "result": "SUCCESS",
  "traceId": "4f2c...",
  "spanId": "91ad..."
}
```

Các trường thường hữu ích:

| Trường | Mục đích |
|---|---|
| `timestamp` | Thời điểm sự kiện, nên thống nhất múi giờ và định dạng. |
| `level` | Mức độ nghiêm trọng theo quy ước logging. |
| `service.name`, `service.version`, `deployment.environment` | Xác định dịch vụ và phiên bản đã phát sinh log. |
| `event.name`, `event.version` | Định danh ổn định và phiên bản schema của sự kiện. |
| `result`, `reason.code` | Kết quả hoặc lý do đã chuẩn hóa. |
| `booking.id` hoặc định danh nghiệp vụ tương ứng | Tìm các log liên quan đến một thực thể, nếu chính sách dữ liệu cho phép. |
| `traceId`, `spanId` | Mở trace tương ứng và xác định span phát sinh log. |
| `error.type`, `error.code` | Phân loại lỗi mà không phụ thuộc hoàn toàn vào message. |
| `duration.ms` | Thời gian xử lý của thao tác khi có ý nghĩa điều tra. |

Tên trường phải nhất quán giữa các dịch vụ. Không nên lúc dùng `bookingId`, lúc dùng `booking_id`, lúc lại nhúng mã đơn vào message. Chọn một schema chung và duy trì nó qua các lần thay đổi.

`event.name` cần mô tả sự kiện đã xảy ra, ví dụ `rental.booking.confirmed` hoặc `rental.payment.authorization.failed`. Không đặt tên sự kiện theo tên class Java, tên method hay câu message vì các chi tiết đó dễ thay đổi khi refactor.

Message dành cho người đọc; các trường dành cho máy truy vấn. Có thể giữ message ngắn như `Booking confirmed`, đồng thời đưa trạng thái, kết quả và mã đơn vào key-value riêng.

## 4. Chọn log level theo ý nghĩa vận hành

| Level | Dùng khi | Ví dụ |
|---|---|---|
| `ERROR` | Một thao tác quan trọng thất bại ngoài dự kiến hoặc cần can thiệp. | Không thể ghi dữ liệu sau khi đã cạn retry. |
| `WARN` | Có tình huống bất thường cần chú ý nhưng ứng dụng vẫn xử lý được. | Đối tác timeout lần đầu và hệ thống chuyển sang retry. |
| `INFO` | Sự kiện vận hành hoặc chuyển trạng thái quan trọng. | Đơn thuê được xác nhận sau khi giao dịch commit. |
| `DEBUG` | Chi tiết phục vụ chẩn đoán khi cần bật có kiểm soát. | Nhánh quy tắc được chọn trong một bộ tính phí. |
| `TRACE` | Dữ liệu rất chi tiết, thường có volume cao. | Diễn biến nội bộ từng bước của một thuật toán. |

Không ghi mọi trường hợp từ chối nghiệp vụ ở mức `ERROR`. Nếu khách hàng gửi yêu cầu không hợp lệ và hệ thống từ chối đúng quy tắc, đó có thể là `INFO` hoặc `WARN` tùy tác động vận hành. Ngược lại, nếu một lỗi nội bộ khiến đơn không thể chuyển trạng thái, `ERROR` có thể phù hợp.

Level cũng là một phần của ngân sách dữ liệu. `DEBUG` hoặc `TRACE` bật trên toàn bộ production có thể làm tăng volume nhanh chóng. Nên giới hạn theo package, thời gian, mẫu lưu hoặc cấu hình có kiểm soát.

## 5. Ghi log đúng thời điểm trong Spring Boot

Với sự kiện thành công gắn với dữ liệu giao dịch, thời điểm ghi log rất quan trọng. Nếu ghi `Booking confirmed` ngay sau câu lệnh `save()` nhưng transaction sau đó rollback, log sẽ mô tả một trạng thái chưa từng được commit.

Một cách phù hợp là phát application event trong transaction và ghi log ở pha `AFTER_COMMIT`:

```java
public record BookingConfirmedEvent(
        UUID bookingId,
        BookingStatus previousStatus,
        BookingStatus currentStatus
) {}
```

Trong service, chỉ phát event sau khi đã áp dụng thay đổi:

```java
@Service
public class BookingService {

    private final BookingRepository repository;
    private final ApplicationEventPublisher eventPublisher;

    public BookingService(
            BookingRepository repository,
            ApplicationEventPublisher eventPublisher
    ) {
        this.repository = repository;
        this.eventPublisher = eventPublisher;
    }

    @Transactional
    public Booking confirm(UUID bookingId) {
        Booking booking = repository.findById(bookingId)
                .orElseThrow(() -> new BookingNotFoundException(bookingId));

        BookingStatus previousStatus = booking.getStatus();

        if (previousStatus != BookingStatus.PENDING) {
            throw new InvalidBookingStateException(bookingId, previousStatus);
        }

        booking.confirm();
        Booking saved = repository.save(booking);

        eventPublisher.publishEvent(new BookingConfirmedEvent(
                saved.getId(),
                previousStatus,
                saved.getStatus()
        ));

        return saved;
    }
}
```

Listener ghi log sau khi transaction commit:

```java
@Component
public class BookingLogListener {

    private static final Logger log =
            LoggerFactory.getLogger(BookingLogListener.class);

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onBookingConfirmed(BookingConfirmedEvent event) {
        log.atInfo()
                .addKeyValue("event.name", "rental.booking.confirmed")
                .addKeyValue("event.version", 1)
                .addKeyValue("booking.id", event.bookingId())
                .addKeyValue("state.from", event.previousStatus())
                .addKeyValue("state.to", event.currentStatus())
                .addKeyValue("result", "SUCCESS")
                .log("Booking confirmed");
    }
}
```

Ví dụ dùng fluent logging API của SLF4J 2.x. Các key-value chỉ trở thành trường có thể truy vấn nếu logging backend được cấu hình để xuất chúng; định dạng console mặc định không nhất thiết là JSON. Hãy cấu hình Logback, Log4j2 hoặc encoder đang dùng để giữ các trường này trong output có cấu trúc.

Listener trên chạy đồng bộ ở luồng commit theo cấu hình mặc định. Nếu chuyển listener sang xử lý bất đồng bộ, cần kiểm tra việc truyền trace context và MDC qua ranh giới thread. Cũng cần hiểu giới hạn của application event trong bộ nhớ: nếu yêu cầu là bảo đảm lưu lại mọi sự kiện nghiệp vụ ngay cả khi tiến trình dừng đột ngột, hãy dùng transactional outbox hoặc cơ chế lưu bền vững phù hợp. Log vận hành không thay thế nguồn dữ liệu nghiệp vụ hay audit trail.

Với một quyết định bị từ chối, có thể ghi log ngay tại nơi hệ thống đưa ra quyết định vì bản thân lần từ chối là sự kiện cần điều tra:

```java
log.atWarn()
        .addKeyValue("event.name", "rental.booking.confirm.rejected")
        .addKeyValue("booking.id", bookingId)
        .addKeyValue("booking.status", previousStatus)
        .addKeyValue("reason.code", "INVALID_STATE")
        .log("Booking confirmation rejected");
```

Message ở đây mô tả một lần thử bị từ chối, không khẳng định đơn đã thay đổi trạng thái.

## 6. Kết hợp log với Micrometer Observation và tracing

Micrometer Observation cung cấp một điểm tích hợp để quan sát thao tác trong ứng dụng. Khi registry được cấu hình với các handler phù hợp, một Observation có thể đóng góp dữ liệu cho metrics và tracing. Log bổ sung chi tiết sự kiện mà không biến từng giá trị định danh thành nhãn metric.

Ví dụ, có thể đặt Observation quanh thao tác xác nhận:

```java
public Booking confirm(UUID bookingId, BookingType bookingType) {
    return Observation.createNotStarted(
                    "rental.booking.confirm",
                    observationRegistry
            )
            .lowCardinalityKeyValue("booking.type", bookingType.name())
            .observe(() -> bookingService.confirm(bookingId));
}
```

Tên Observation và các low-cardinality key-value phải ổn định, với số lượng giá trị hữu hạn. `booking.type` phù hợp nếu chỉ có một tập loại đơn thuê được kiểm soát. Không đưa `booking.id`, `customer.id`, email hoặc URL chứa mã định danh vào low-cardinality key-value vì mỗi giá trị mới có thể tạo thêm chuỗi thời gian metrics.

Khi Micrometer Tracing được cấu hình, trace context có thể được đưa vào MDC để logging backend thêm `traceId` và `spanId` vào log. Nhờ vậy, từ một log có thể mở trace tương ứng. Hãy xác minh pattern hoặc encoder thực tế có xuất các trường này; không giả định mọi cấu hình logging đều tự động làm việc đó.

Một số nguyên tắc tương quan:

- Dùng `traceId` và `spanId` do tracing context cung cấp. Không tự sinh một trace ID mới cho mỗi dòng log.
- Với tác vụ chạy ngoài HTTP request, như scheduler hoặc consumer, hãy bảo đảm tác vụ có context tương quan riêng và context được truyền qua các ranh giới bất đồng bộ.
- Nếu cần định danh quy trình nghiệp vụ kéo dài qua nhiều request, dùng correlation ID hoặc workflow ID có quy ước rõ ràng.
- Không dùng trace ID, booking ID hoặc customer ID làm metric tag.
- Trace sampling có thể khiến một số trace không được lưu. Nếu log của một sự kiện quan trọng vẫn cần được giữ, hãy đặt chính sách lưu log độc lập với việc trace có được sample hay không.

Không phải mọi dòng log đều cần mở một Observation riêng. Hãy tạo Observation quanh thao tác có ý nghĩa về độ trễ hoặc kết quả; ghi log tại các điểm sự kiện cần giải thích. Hai tín hiệu nên bổ sung cho nhau.

## 7. Phân biệt log vận hành với audit log

Log vận hành phục vụ quan sát hệ thống: điều tra lỗi, độ trễ, retry và các chuyển trạng thái quan trọng. Audit log phục vụ chứng minh ai đã thực hiện hành động nào, vào thời điểm nào, trên đối tượng nào và theo quyền hạn nào. Hai loại dữ liệu có thể dùng chung một số trường, nhưng có yêu cầu khác nhau.

Nếu nghiệp vụ yêu cầu lưu lịch sử thay đổi có tính pháp lý hoặc cần chống sửa đổi, không dựa riêng vào SLF4J và hệ thống gom log. Hãy dùng audit trail hoặc bảng lịch sử được thiết kế cho yêu cầu lưu giữ, phân quyền, truy vết và tính toàn vẹn. Log vận hành có thể bị lọc, sampling, xoay vòng hoặc hết hạn theo chính sách lưu trữ.

## 8. Kiểm soát cardinality, quyền riêng tư và chi phí

Log có thể chứa trường định danh chi tiết hơn metrics, nhưng điều đó không có nghĩa là mọi dữ liệu đều nên được ghi.

**Cardinality của metrics:** chỉ dùng nhãn có tập giá trị hữu hạn và dự đoán được, chẳng hạn `result=success|rejected|failed`, `booking.type=short|long` hoặc `payment.provider=provider_a|provider_b`. Tránh `booking.id`, `user.id`, email, request ID và URL đầy đủ. Những giá trị này làm số lượng chuỗi thời gian tăng nhanh, gây tốn bộ nhớ và chi phí lưu trữ.

**Dữ liệu trong log:** chỉ thêm định danh nghiệp vụ khi có nhu cầu điều tra rõ ràng, quyền truy cập phù hợp và thời hạn lưu trữ được xác định. Không ghi:

- Password, access token, refresh token, API key, cookie hoặc header xác thực.
- Số thẻ, mã bảo mật, thông tin ngân hàng hoặc dữ liệu thanh toán nhạy cảm.
- Email, số điện thoại, địa chỉ, giấy tờ định danh hoặc dữ liệu cá nhân không cần thiết.
- Toàn bộ request/response, nội dung file, query string hoặc payload của đối tác nếu chưa được lọc.
- Dữ liệu do người dùng nhập trực tiếp mà chưa được giới hạn và làm sạch.

Dùng mã tham chiếu đã được phê duyệt hoặc dữ liệu đã che/mã hóa khi cần liên kết bản ghi. Không đưa dữ liệu nhạy cảm vào message, exception message hay trường MDC vì các đường này đều có thể được xuất sang hệ thống log.

**Chi phí và volume:** ghi các sự kiện quan trọng ở mức phù hợp, giới hạn log lặp trong vòng retry, tránh ghi mỗi vòng lặp hoặc mỗi bản ghi khi xử lý batch lớn. Với thao tác có volume cao, cân nhắc log tổng kết theo batch hoặc chỉ log các trường hợp bất thường. Không bỏ log của sự kiện quan trọng chỉ vì trace đang được sampling.

## 9. Tránh các mẫu logging gây khó điều tra

| Mẫu không nên dùng | Vấn đề | Cách cải thiện |
|---|---|---|
| `log.info("confirm booking " + booking)` | Có thể in toàn bộ object và dữ liệu nhạy cảm; khó truy vấn trường riêng. | Ghi `event.name`, `booking.id`, trạng thái và kết quả bằng key-value. |
| `log.error("Invalid request", ex)` cho mọi lần từ chối hợp lệ | Làm nhiễu cảnh báo và tăng tỷ lệ lỗi giả. | Dùng level và `reason.code` theo ngữ nghĩa nghiệp vụ. |
| Ghi `Booking confirmed` trước khi transaction commit | Log có thể khẳng định thành công dù dữ liệu rollback. | Ghi sau commit hoặc dùng cơ chế sự kiện bền vững. |
| Ghi cùng exception ở mọi tầng | Tạo nhiều bản ghi trùng, khó xác định nơi xử lý. | Ghi một lần ở tầng xử lý hoặc chuyển đổi lỗi phù hợp. |
| Đưa `booking.id` vào metric tag | Tạo cardinality rất cao. | Giữ ID trong log; metric chỉ dùng nhóm kết quả hoặc loại hữu hạn. |
| Tự ghép `traceId` vào message | Khó truy vấn và dễ sai khi context thay đổi. | Dùng MDC/context do tracing cung cấp và xuất thành trường riêng. |
| Ghi toàn bộ payload của đối tác | Tăng volume và nguy cơ lộ dữ liệu. | Chọn mã giao dịch, mã kết quả và trường đã được cho phép. |

## 10. Quy trình điều tra từ log đến trace

Khi nhận báo cáo một đơn thuê không được xác nhận, có thể điều tra theo trình tự sau:

1. Bắt đầu từ metrics để xác định lỗi có xảy ra diện rộng hay chỉ ảnh hưởng một nhóm yêu cầu. Kiểm tra tỷ lệ thất bại, độ trễ và phân bố theo phiên bản dịch vụ hoặc đối tác.
2. Tìm log theo mã đơn thuê đã được phép sử dụng, khoảng thời gian và `event.name`. Đọc các sự kiện theo thứ tự thời gian để xác định trạng thái trước/sau và `reason.code`.
3. Lấy `traceId` từ log có liên quan rồi mở distributed trace. Kiểm tra span gọi cơ sở dữ liệu, dịch vụ thanh toán hoặc hệ thống bên ngoài để tìm điểm chậm hoặc lỗi.
4. Đối chiếu mã lỗi đã chuẩn hóa với log ở ranh giới tích hợp. Không cần tải toàn bộ payload nếu mã kết quả đã đủ giải thích.
5. Sau khi xử lý, xác nhận metrics trở lại mức bình thường và kiểm tra các sự kiện mới có phản ánh đúng kết quả hay không.

Quy trình này hiệu quả khi timestamp, event name, định danh tương quan và schema được giữ nhất quán giữa các dịch vụ. Đồng hồ của các máy cũng cần được đồng bộ để việc sắp xếp log và trace có ý nghĩa.

## 11. Checklist trước khi thêm một dòng log

Trước khi thêm log cho một thao tác, hãy tự kiểm tra:

- Dòng log này trả lời câu hỏi vận hành cụ thể nào?
- Nó mô tả một sự kiện đã xảy ra, một lần thử, hay một quyết định bị từ chối?
- `event.name` có ổn định và dễ truy vấn không?
- Các trường có kiểu dữ liệu và tên nhất quán không?
- Log được ghi ở thời điểm đúng, đặc biệt với transaction?
- Level có phản ánh mức độ cần chú ý thực tế không?
- Có thể liên kết log với trace bằng context hiện có không?
- Có trường nào tạo cardinality cao trong metrics không?
- Có dữ liệu cá nhân, bí mật hoặc payload không cần thiết không?
- Volume và thời hạn lưu trữ có phù hợp với giá trị điều tra không?

Một bộ log nghiệp vụ tốt giúp trả lời nhanh điều gì đã xảy ra, với đối tượng nào, vì sao và trong ngữ cảnh xử lý nào. Khi chọn log theo sự kiện, giữ schema ổn định và liên kết nó với Observation cùng trace context, đội ngũ có thể điều tra chi tiết mà vẫn kiểm soát được chi phí và rủi ro dữ liệu.

