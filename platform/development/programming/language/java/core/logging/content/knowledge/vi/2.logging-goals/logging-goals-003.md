# Theo dõi nghiệp vụ bằng logging trong Java

## 1. Mục tiêu: hiểu điều gì đã xảy ra với một nghiệp vụ

Logging không chỉ giúp người phát triển tìm lỗi kỹ thuật. Trong một ứng dụng xử lý đơn hàng, thanh toán, đăng ký tài khoản hoặc duyệt hồ sơ, log còn giúp trả lời các câu hỏi mang ý nghĩa nghiệp vụ:

- Đơn hàng đã đi qua những bước nào, dừng ở đâu và vì sao?
- Yêu cầu thanh toán bị từ chối theo quy tắc nào, hay thất bại do sự cố hệ thống?
- Một yêu cầu hủy đơn được tiếp nhận, chấp thuận hay bị từ chối?
- Khi khách hàng phản ánh một vấn đề, có thể lần theo các thao tác liên quan bằng mã đơn hàng hoặc mã tương quan không?
- Một quy trình tự động đã bắt đầu, hoàn tất, bị bỏ qua hay cần xử lý lại?

**Theo dõi nghiệp vụ bằng logging** là ghi lại các sự kiện có ý nghĩa đối với luồng xử lý và trạng thái nghiệp vụ, kèm thông tin đủ để giải thích bối cảnh và kết quả. Mục đích chính là **quan sát và điều tra**: thấy được những gì ứng dụng đã xử lý, đối chiếu với trạng thái hiện tại, phát hiện luồng bất thường và hỗ trợ vận hành.

Ví dụ, log kỹ thuật `Connection timed out` cho biết kết nối gặp lỗi; log nghiệp vụ `payment_authorization_failed` với `order_id`, `correlation_id` và `reason_code` cho biết bước nào của đơn hàng bị ảnh hưởng. Hai loại log bổ sung cho nhau: log nghiệp vụ trả lời *việc gì*, log kỹ thuật hỗ trợ tìm *nguyên nhân kỹ thuật*.

> Log ứng dụng không mặc nhiên là sổ cái, nguồn trạng thái nghiệp vụ chính thức hoặc bằng chứng kiểm toán bất biến. Việc ghi log có thể thất bại, trùng lặp, đến chậm hoặc bị xóa theo chính sách lưu trữ.

## 2. Nhận diện những sự kiện đáng ghi

Hãy bắt đầu từ **vòng đời của đối tượng nghiệp vụ** (đơn hàng, phiếu yêu cầu, hóa đơn), không bắt đầu bằng số lượng dòng code. Với quy trình thanh toán đơn hàng, một luồng minh họa là:

```text
checkout_started
    |
    +-- payment_authorized --> order_paid
    |
    +-- payment_declined   --> giữ nguyên trạng thái chưa thanh toán
```

Mỗi mũi tên chỉ một bước xử lý hoặc một kết quả có thể quan sát. Trong ứng dụng thật, `order_paid` chỉ được coi là sự kiện đã xảy ra khi hệ thống thực sự hoàn tất thay đổi trạng thái theo quy tắc giao dịch của mình; phản hồi chấp thuận từ cổng thanh toán chưa chắc đồng nghĩa đơn hàng đã được ghi nhận là đã thanh toán.

Các nhóm sự kiện thường hữu ích:

| Nhóm | Ví dụ | Câu hỏi hỗ trợ |
| --- | --- | --- |
| Bắt đầu thao tác | `checkout_started`, `refund_requested` | Quy trình được gọi khi nào, cho đối tượng nào? |
| Chuyển trạng thái | `order_paid`, `shipment_dispatched` | Đối tượng đã chuyển sang trạng thái nào? |
| Quyết định theo quy tắc | `coupon_rejected`, `cancellation_denied` | Vì sao hệ thống chấp thuận hoặc từ chối? |
| Kết quả tích hợp | `payment_authorized`, `payment_declined` | Dịch vụ bên ngoài trả về loại kết quả nào? |
| Xử lý nền | `invoice_generation_completed`, `retry_scheduled` | Công việc tự động hoàn tất hay đang chờ xử lý? |

Không cần log mọi phép gán biến, vòng lặp hoặc thao tác nhỏ. Nên ghi ở các **ranh giới nghiệp vụ**: khi nhận một yêu cầu quan trọng, khi áp dụng quy tắc và đưa ra quyết định, khi trạng thái thay đổi thành công, khi quy trình kết thúc hoặc gặp kết quả bất thường. Tên sự kiện phải mô tả một việc cụ thể, có quy ước ổn định.

Phân biệt **kết quả nghiệp vụ dự kiến** và **sự cố kỹ thuật**. Khách nhập mã giảm giá hết hạn hoặc ngân hàng từ chối thanh toán có thể là kết quả bình thường của quy trình, thường phù hợp với mức `INFO`. Mất kết nối cơ sở dữ liệu, lỗi lập trình hoặc một trạng thái không thể xảy ra mới cần cảnh báo/ghi lỗi ở mức tương ứng. Không biến mọi kết quả `DECLINED` thành `ERROR`.

## 3. Một bản ghi cần những thông tin gì?

Một dòng `"Đã xử lý đơn hàng"` rất khó dùng khi có hàng nghìn đơn hàng đồng thời. Nên thống nhất các trường dữ liệu:

| Trường | Ý nghĩa và nguyên tắc |
| --- | --- |
| `event` | Tên sự kiện ổn định, ví dụ `order_paid` |
| `order_id` hoặc `entity_id` | Định danh của đối tượng nghiệp vụ để tra cứu vòng đời |
| `correlation_id` | Định danh nối các bước log cùng một luồng yêu cầu; truyền tiếp qua các thành phần liên quan |
| `outcome` | Kết quả có cấu trúc như `STARTED`, `SUCCESS`, `DECLINED`, `FAILED` |
| `reason_code` | Mã lý do ổn định, ví dụ `PAYMENT_NOT_AUTHORIZED`; dễ thống kê hơn câu văn tùy ý |
| `timestamp`, `service`, `environment` | Thời điểm, nơi phát sinh; thường do bộ ghi log hoặc hệ thống thu thập bổ sung |
| `duration_ms` | Thời lượng của bước khi cần tìm điểm nghẽn |
| `actor_role` hoặc mã chủ thể an toàn | Chỉ bổ sung nếu thực sự cần cho nghiệp vụ và phù hợp chính sách bảo vệ dữ liệu |

**`order_id` và `correlation_id` có vai trò khác nhau.** Một đơn hàng có thể được xem, thanh toán, giao hàng trong nhiều yêu cầu; nó giữ nguyên `order_id`. Mỗi luồng thực thi có thể có `correlation_id` riêng để lần theo nhiều lời gọi, luồng xử lý hoặc dịch vụ. Khi có cơ chế thử lại/idempotency, cần thêm mã thao tác (`operation_id` hoặc `idempotency_key` thích hợp) để phân biệt các lần thử và tránh đếm nhầm một hành động.

Một bản ghi có cấu trúc máy đọc được có thể trông như sau (ví dụ minh họa, không phải đầu ra của chương trình bên dưới):

```json
{
  "timestamp": "2026-11-09T12:00:00Z",
  "level": "INFO",
  "service": "order-service",
  "event": "order_paid",
  "order_id": "ORD-101",
  "correlation_id": "corr-a1",
  "outcome": "SUCCESS"
}
```

Có thể dùng JSON hoặc các cặp `key=value` nhất quán. Trong hệ thống thực tế, nên dùng thư viện/hệ thống logging có hỗ trợ trường có cấu trúc và mã hóa giá trị đúng cách. Không tự nối dữ liệu đầu vào chưa kiểm soát vào dòng log: ký tự xuống dòng hoặc dấu phân cách có thể làm sai bản ghi và gây *log injection*. Ví dụ sau chỉ dùng các mã cố định, an toàn để minh họa khái niệm.

## 4. Ví dụ Java 17+: ghi lại luồng thanh toán mô phỏng

Chương trình dùng `java.util.logging` có sẵn trong JDK, không cần thư viện ngoài. Nó mô phỏng hai lần thanh toán: một lần được chấp thuận và một lần bị từ chối. Mỗi sự kiện có tên rõ ràng, mã đơn hàng, mã tương quan và kết quả.

Lưu thành tệp **`BusinessLoggingDemo.java`**:

```java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class BusinessLoggingDemo {
    private static final Logger LOG =
            Logger.getLogger(BusinessLoggingDemo.class.getName());

    private static void configureLogger() {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        ConsoleHandler handler = new ConsoleHandler();
        handler.setLevel(Level.INFO);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " "
                        + formatMessage(record)
                        + System.lineSeparator();
            }
        });
        LOG.addHandler(handler);
    }

    private static void checkout(
            String orderId, String correlationId, boolean paymentApproved) {
        LOG.info(() -> "event=checkout_started order_id=" + orderId
                + " correlation_id=" + correlationId
                + " outcome=STARTED");

        if (!paymentApproved) {
            LOG.info(() -> "event=payment_declined order_id=" + orderId
                    + " correlation_id=" + correlationId
                    + " outcome=DECLINED"
                    + " reason_code=PAYMENT_NOT_AUTHORIZED");
            return;
        }

        LOG.info(() -> "event=payment_authorized order_id=" + orderId
                + " correlation_id=" + correlationId
                + " outcome=SUCCESS");

        // Mô phỏng việc đơn hàng được chuyển sang PAID trong bộ nhớ.
        LOG.info(() -> "event=order_paid order_id=" + orderId
                + " correlation_id=" + correlationId
                + " outcome=SUCCESS");
    }

    public static void main(String[] args) {
        configureLogger();

        checkout("ORD-101", "corr-a1", true);
        checkout("ORD-102", "corr-b2", false);
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 BusinessLoggingDemo.java
java BusinessLoggingDemo
```

Năm dòng sau được ghi ra **stderr** qua `ConsoleHandler` (không phải stdout); bộ định dạng trong ví dụ cố ý chỉ in mức log và thông điệp để đầu ra ổn định:

```text
INFO event=checkout_started order_id=ORD-101 correlation_id=corr-a1 outcome=STARTED
INFO event=payment_authorized order_id=ORD-101 correlation_id=corr-a1 outcome=SUCCESS
INFO event=order_paid order_id=ORD-101 correlation_id=corr-a1 outcome=SUCCESS
INFO event=checkout_started order_id=ORD-102 correlation_id=corr-b2 outcome=STARTED
INFO event=payment_declined order_id=ORD-102 correlation_id=corr-b2 outcome=DECLINED reason_code=PAYMENT_NOT_AUTHORIZED
```

Cách đọc ví dụ:

1. Tìm `order_id=ORD-101` sẽ thấy một luồng bắt đầu, được chấp thuận và đi tới `order_paid`.
2. Tìm `order_id=ORD-102` sẽ thấy yêu cầu bắt đầu nhưng kết thúc bằng `payment_declined`; vì đây là kết quả từ chối dự kiến nên chương trình dùng `INFO`.
3. Tìm `correlation_id=corr-a1` sẽ gom được các bước của cùng một lần xử lý ORD-101. Trong ứng dụng web, mã này thường được tạo hoặc tiếp nhận tại điểm vào request rồi truyền xuyên suốt các lớp xử lý; không dùng một biến `static` dùng chung để chứa mã request đang chạy.
4. Các biểu thức `LOG.info(() -> ...)` sử dụng `Supplier<String>`; thông điệp chỉ được tạo khi mức log cho phép ghi, hữu ích khi việc xây dựng thông điệp tốn chi phí.

**Giới hạn của ví dụ:** `checkout` ở đây là mô phỏng, không gọi cổng thanh toán và không ghi cơ sở dữ liệu. Dòng `order_paid` chỉ cho thấy một nhánh code đã chạy. Trong hệ thống thật, việc thông báo “đơn đã thanh toán” phải dựa vào kết quả giao dịch/điều kiện trạng thái đã xác nhận; một dòng log xuất hiện không đủ để chứng minh dữ liệu đã lưu bền vững. Ví dụ cũng không tự thêm thời gian hay mã dịch vụ; hệ thống logging của ứng dụng thật nên cung cấp các trường đó.

## 5. Dùng log để điều tra một vấn đề nghiệp vụ

Giả sử khách hàng báo: “Tôi đã thanh toán nhưng đơn hàng vẫn ở trạng thái chờ.” Một cách kiểm tra hợp lý là:

1. Xác định `order_id` từ hệ thống quản lý đơn hàng bằng cách hợp lệ, rồi lọc log theo mã đó trong khoảng thời gian phù hợp.
2. Xem thứ tự sự kiện: có `checkout_started` không, có `payment_authorized` không, có `order_paid` không? Kiểm tra `correlation_id` để đi theo từng lượt xử lý và liên kết các dịch vụ nếu có.
3. Nếu chỉ thấy `payment_authorized` mà chưa có `order_paid`, điều tra bước cập nhật/trả về trạng thái và log kỹ thuật liên quan. Chưa kết luận đơn hàng bị mất nếu chưa đối chiếu cơ sở dữ liệu.
4. Nếu cùng một sự kiện xuất hiện nhiều lần, kiểm tra cơ chế thử lại, xử lý lại thông điệp và khóa chống xử lý trùng. **Nhiều dòng log không mặc nhiên có nghĩa nhiều giao dịch thành công.**
5. Đối chiếu trạng thái chính thức của đơn, kết quả từ nhà cung cấp thanh toán và bản ghi kế toán/kiểm toán theo quy trình của hệ thống trước khi đưa ra kết luận cho khách hàng.

Một số bộ lọc hữu ích trên nền tảng thu thập log là:

```text
order_id=ORD-101
correlation_id=corr-a1
event=payment_declined reason_code=PAYMENT_NOT_AUTHORIZED
event=order_paid
```

Cú pháp tìm kiếm cụ thể tùy công cụ. Để kiểm tra quy trình nhiều dịch vụ, cần đồng bộ đồng hồ ở mức hợp lý, lưu timestamp có múi giờ rõ ràng (thường UTC), bảo toàn ngữ cảnh tương quan qua luồng bất đồng bộ và biết rằng thứ tự log nhận được có thể khác thứ tự sự kiện thực tế.

Log có thể giúp nhận ra xu hướng như tăng số lần từ chối thanh toán hoặc nhiều yêu cầu bị kẹt ở một bước. Tuy nhiên, số liệu thống kê từ log chỉ đáng tin khi đã kiểm soát việc mất bản ghi, ghi trùng, lấy mẫu và chính sách lưu giữ.

## 6. Phân biệt log nghiệp vụ với các nguồn dữ liệu khác

| Cơ chế | Mục đích chính | Điểm cần nhớ |
| --- | --- | --- |
| **Log nghiệp vụ** | Quan sát đường đi, bối cảnh, kết quả xử lý để tra cứu và điều tra | Có thể mất, trùng, đổi thứ tự; không mặc nhiên là nguồn dữ liệu chính thức |
| **Trạng thái trong cơ sở dữ liệu** | Biểu diễn trạng thái nghiệp vụ hiện tại theo giao dịch | Phải được đọc/kiểm tra theo quy tắc nhất quán của hệ thống |
| **Audit trail** | Ghi nhận có kiểm soát ai thực hiện hành động gì, khi nào, với kết quả nào | Cần chính sách lưu giữ, truy cập, toàn vẹn và quy trình phù hợp yêu cầu kiểm toán |
| **Domain event / message** | Công bố sự kiện để thành phần khác phản ứng | Thường cần định danh sự kiện, cơ chế phát hành đáng tin cậy và xử lý lặp |
| **Metric** | Đo tổng số, tỷ lệ, độ trễ, tình trạng vận hành theo thời gian | Phù hợp cho bảng điều khiển và cảnh báo tổng hợp; ít bối cảnh của từng đối tượng |
| **Trace phân tán** | Theo dõi chuỗi lời gọi, thời gian và mối quan hệ giữa các bước | Bổ trợ rất tốt khi cần tìm vị trí chậm/lỗi xuyên dịch vụ |

Ví dụ, doanh thu chính thức không nên được tính bằng cách đếm các dòng `order_paid` rồi nhân với giá trị đơn hàng. Một ứng dụng có thể log xong nhưng lỗi ở bước ghi dữ liệu, hoặc giao dịch đã commit trong khi hệ thống ghi log gặp trục trặc. Nếu nghiệp vụ cần bảo đảm phát sự kiện sau khi thay đổi dữ liệu, có thể nghiên cứu **transactional outbox** (ghi trạng thái và bản ghi outbox trong cùng giao dịch, rồi phát sự kiện sau); đây là giải pháp nhất quán dữ liệu/sự kiện, không phải thuộc tính tự có của logger.

## 7. Các nguyên tắc thiết kế khi triển khai thực tế

**Ghi đúng thời điểm.** Dùng tên sự kiện mô tả điều đã thực sự xảy ra. Không ghi `order_paid` trước khi xác nhận bước cập nhật trạng thái thành công. Khi thao tác thất bại, ghi kết quả và mã lý do tương ứng; các nhánh bị từ chối theo quy tắc không được gắn nhãn thành công.

**Ổn định cấu trúc.** Quy định tên sự kiện và tập mã `outcome`/`reason_code` dùng chung; tránh mỗi nhóm tự đặt một câu văn khác nhau. Khi nâng cấp schema, quản lý phiên bản nếu công cụ phân tích phụ thuộc vào trường cũ. Một mã định danh phải nhất quán giữa các bước xử lý có liên quan.

**Bảo vệ dữ liệu.** Chỉ ghi dữ liệu tối thiểu cần cho mục đích điều tra. Không đưa mật khẩu, token, số thẻ thanh toán, mã OTP, thông tin cá nhân nhạy cảm hay toàn bộ nội dung request/response vào log. Cân nhắc ẩn danh hoặc thay bằng mã định danh phù hợp; phân quyền truy cập, mã hóa và thời hạn lưu giữ. Chuẩn hóa/escape dữ liệu đầu vào để tránh tạo dòng log giả hoặc phá cấu trúc bản ghi.

**Chọn mức log theo hành vi.** `INFO` cho những bước và kết quả bình thường đáng theo dõi; `WARNING` cho hiện tượng bất thường cần chú ý nhưng hệ thống còn xử lý được; `SEVERE` trong `java.util.logging` cho lỗi nghiêm trọng. Với framework khác, tên mức có thể là `WARN`/`ERROR`. Không ghi stack trace ở mọi lần khách nhập sai dữ liệu hợp lệ về mặt kỹ thuật.

**Kiểm soát chi phí.** Log mọi thao tác của từng bản ghi có thể tạo lưu lượng lớn, tăng thời gian xử lý và chi phí lưu trữ. Chọn các điểm có giá trị nghiệp vụ, tránh ghi lặp không cần thiết và dùng chính sách giới hạn/lấy mẫu có chủ đích. Nếu cần đối chiếu số liệu chính thức, không dựa vào luồng log đã lấy mẫu.

**Đảm bảo khả năng truy vết.** Đối tượng có `entity_id`, mỗi lần xử lý có `correlation_id` và khi cần có `operation_id`. Với tác vụ bất đồng bộ, phải truyền ngữ cảnh qua hàng đợi/công việc nền; không giả định ngữ cảnh luồng tự đi theo khi đổi thread. Log lỗi nên ghi loại lỗi và mã nguyên nhân hữu ích cho người vận hành mà không tiết lộ bí mật.

## 8. Sai lầm thường gặp và cách sửa

- **Chỉ ghi “Thành công/Thất bại”.** Không đủ để tìm một trường hợp cụ thể. Thêm `event`, định danh đối tượng, mã tương quan, `outcome` và mã nguyên nhân khi có.
- **Ghi thành công trước khi giao dịch hoàn tất.** Làm người vận hành hiểu sai tình trạng thực. Chọn vị trí ghi tương ứng với cam kết trạng thái thật; khi cần bảo đảm sự kiện bền vững, dùng cơ chế chuyên dụng.
- **Dùng log để thay cơ sở dữ liệu hoặc audit trail.** Log phục vụ quan sát; nghiệp vụ tài chính và kiểm toán phải dựa vào dữ liệu/cơ chế có bảo đảm phù hợp.
- **Đánh dấu mọi từ chối là lỗi hệ thống.** Phân biệt quyết định nghiệp vụ dự kiến với lỗi kỹ thuật để không tạo cảnh báo giả.
- **Ghi toàn bộ đối tượng hoặc dữ liệu khách hàng.** Dễ rò rỉ thông tin, làm log phình to và khó tìm kiếm. Ghi các trường được chọn, đã xử lý dữ liệu nhạy cảm.
- **Không nối các bước bằng mã tương quan.** Khi có nhiều request đồng thời, các dòng xen kẽ khiến việc điều tra khó khăn. Truyền mã theo đúng luồng thực thi.
- **Đếm log thành số giao dịch hoàn tất.** Retry, log trùng và mất log làm sai kết quả. Đối chiếu nguồn trạng thái chính thức và định danh sự kiện duy nhất.

## 9. Tự kiểm tra

1. Một đơn hàng có `payment_authorized` nhưng chưa có `order_paid`. Có thể kết luận đã thanh toán thành công chưa? **Chưa**: cần xác nhận điều kiện cập nhật trạng thái của hệ thống và dữ liệu chính thức.
2. Khách nhập mã ưu đãi hết hạn. Nên ghi sự kiện gì? Một lựa chọn là `coupon_rejected` với `outcome=DECLINED` và `reason_code=EXPIRED` ở mức `INFO`, kèm định danh ngữ cảnh an toàn.
3. Hai request cùng thao tác với ORD-101. Trường nào giúp gom toàn bộ vòng đời đơn, trường nào giúp tách từng lượt thực thi? **`order_id`** gom theo đơn hàng; **`correlation_id`** phân biệt các luồng xử lý.
4. Nếu một lần thanh toán bị retry và xuất hiện hai dòng `payment_authorized`, có thể đếm thành hai khoản thu không? **Không**. Phải xác minh mã giao dịch và trạng thái chính thức, kèm quy tắc chống xử lý trùng.
5. Khi cần truy vết trên môi trường thật, câu hỏi cần trả lời được là: **Sự kiện nào xảy ra, với đối tượng nào, trong luồng nào, khi nào, có kết quả và lý do gì?** Nếu log chưa trả lời được, hãy cải thiện cấu trúc ở đúng ranh giới nghiệp vụ.

**Ý chính:** Log nghiệp vụ có giá trị khi nó ghi đúng các sự kiện và quyết định có ý nghĩa, có định danh để lần theo, phản ánh kết quả trung thực và tôn trọng giới hạn của logging. Nó giúp giải thích quá trình xử lý; trạng thái chính thức, tính nhất quán giao dịch và kiểm toán cần được bảo đảm bằng các cơ chế phù hợp.
