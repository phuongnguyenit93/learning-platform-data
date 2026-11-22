# Ghi nhận hành vi hệ thống bằng Java Logging

## 1. Ghi nhận hành vi hệ thống là gì và để làm gì?

Trong một chương trình Java, *hành vi hệ thống* là những sự kiện và quyết định có ý nghĩa khi chương trình vận hành: ứng dụng khởi động, nhận yêu cầu, kiểm tra dữ liệu, chấp nhận hoặc từ chối thao tác, gọi dịch vụ phụ thuộc, thay đổi trạng thái nghiệp vụ, hoàn tất yêu cầu hay gặp lỗi.

**Logging** tạo ra các bản ghi có thời điểm, mức độ, nguồn phát sinh và ngữ cảnh để trả lời những câu hỏi như:

- Hệ thống đã nhận yêu cầu nào, vào lúc nào và kết quả cuối cùng là gì?
- Một đơn hàng bị từ chối vì quy tắc nghiệp vụ nào?
- Một lời gọi cơ sở dữ liệu hoặc dịch vụ bên ngoài có lỗi hay chậm không?
- Các bản ghi ở nhiều lớp hoặc nhiều dịch vụ thuộc cùng một luồng xử lý nào?
- Khi sự cố xảy ra, diễn biến nào dẫn đến lỗi và cần điều tra ở đâu?

Mục tiêu là tạo **chuỗi bằng chứng vận hành đủ để hiểu điều gì xảy ra và tại sao**, đồng thời giữ chi phí, độ nhiễu và rủi ro lộ dữ liệu ở mức chấp nhận được. Logging không thay thế debugger, metric hay distributed tracing; mỗi cơ chế trả lời một loại câu hỏi khác nhau.

## 2. Chọn các sự kiện đáng ghi

Không cần ghi mọi câu lệnh hay mọi lần gọi hàm. Hãy ưu tiên **ranh giới xử lý, quyết định nghiệp vụ, thay đổi trạng thái và bất thường có thể hành động**.

| Nhóm sự kiện | Ví dụ tên sự kiện ổn định | Thông tin cần thiết | Mức tham khảo |
| --- | --- | --- | --- |
| Vòng đời ứng dụng | app.started, app.stopping | service, version, environment | INFO |
| Tiếp nhận và hoàn tất yêu cầu | request.received, request.completed | requestId, route dạng mẫu, status, durationMs | INFO hoặc DEBUG tùy lưu lượng |
| Quyết định nghiệp vụ | order.accepted, order.rejected | orderId, outcome, reasonCode | INFO |
| Thao tác với phụ thuộc | inventory.call.failed, storage.retrying | dependency, attempt, errorCode, durationMs | WARNING hoặc SEVERE theo tác động |
| Thay đổi trạng thái đáng chú ý | payment.confirmed, job.completed | đối tượng, trạng thái trước/sau, correlation ID | INFO |
| Sự kiện bảo mật | auth.denied, rate_limit.triggered | loại hành động, lý do, định danh đã giảm thiểu dữ liệu | INFO hoặc WARNING tùy chính sách |
| Bất thường và lỗi | order.persist.failed, queue.consumer.failed | operation, errorCode, exception, requestId | WARNING hoặc SEVERE |
| Thông tin chẩn đoán chi tiết | cache.lookup, mapper.input.shape | tên thành phần, thời lượng, số lượng | FINE/DEBUG, chỉ bật khi cần |

**Chú ý:** Một lần người dùng nhập sai dữ liệu là kết quả nghiệp vụ dự kiến, thường ghi INFO (hoặc thấp hơn), chưa đủ lý do để coi là lỗi hệ thống. WARNING dành cho điều kiện bất thường có thể cần chú ý; SEVERE dành cho lỗi nghiêm trọng ảnh hưởng xử lý. Không ghi INFO cho từng vòng lặp, từng phần tử hay mọi truy vấn khi lượng dữ liệu lớn.

Mỗi sự kiện nên cho biết: **điều gì xảy ra → ở đâu → đối tượng nào → kết quả ra sao → vì sao**, trong giới hạn thông tin an toàn. Tên sự kiện nên diễn tả hành động đã xảy ra, ví dụ order.rejected, thay vì thông điệp mơ hồ như "Something went wrong".

## 3. Thiết kế bản ghi dễ tìm kiếm và liên kết

Một log vận hành hữu ích thường gồm:

- **timestamp**: thời điểm phát sinh; khi lưu tập trung nên dùng thời gian nhất quán, ưu tiên UTC theo ISO 8601.
- **level**: mức quan trọng của sự kiện.
- **service/logger**: dịch vụ và lớp/thành phần phát sinh.
- **event**: tên sự kiện ổn định, ví dụ order.rejected.
- **requestId/correlationId**: định danh liên kết những bản ghi của cùng một yêu cầu hoặc quy trình.
- **traceId/spanId**: khi có hệ thống distributed tracing; không tự xuất hiện chỉ vì dùng Java logging.
- **business identifier**: mã đơn hàng hoặc mã tác vụ không nhạy cảm, chỉ ghi khi thực sự cần.
- **outcome/reasonCode**: SUCCESS, REJECTED, FAILED và mã lý do máy có thể tìm kiếm.
- **durationMs, attempt, dependency**: số liệu cần để phân tích độ trễ, retry hoặc lỗi tích hợp.
- **exception**: loại lỗi và stack trace tại vị trí phù hợp, nhất là lỗi bất ngờ.

Ví dụ một **bản ghi JSON minh họa về định dạng**, không phải đầu ra mặc định của java.util.logging:

~~~json
{
  "timestamp": "2026-11-09T12:00:00Z",
  "level": "INFO",
  "service": "order-service",
  "event": "order.rejected",
  "requestId": "req-b2",
  "orderId": "ord-102",
  "outcome": "REJECTED",
  "reasonCode": "INVALID_QUANTITY"
}
~~~

Giữ **tên khóa và mã sự kiện ổn định** giữa các phiên bản để dashboard, truy vấn và cảnh báo không bị hỏng. Dùng giá trị có kiểu phù hợp (durationMs là số trong JSON), và thống nhất đơn vị. Khi hệ thống chưa hỗ trợ JSON logger, có thể ghi thông điệp dạng key=value; tuy nhiên muốn lọc theo trường một cách tin cậy ở quy mô lớn thì cần formatter/encoder hoặc pipeline phân tích log phù hợp.

Không đưa mật khẩu, token, khóa API, cookie phiên, dữ liệu thẻ, toàn bộ payload cá nhân, hoặc thông tin nhạy cảm không cần thiết vào log. Giảm thiểu, che hoặc băm định danh theo chính sách áp dụng. Kiểm tra đầu vào không tin cậy để tránh xuống dòng giả mạo log (log injection); dùng mã sự kiện và reasonCode kiểm soát được thay cho việc nối trực tiếp thông báo tùy ý từ phía người dùng.

## 4. Mức log trong Java

Java SE có **java.util.logging (JUL)** với các mức thường gặp: SEVERE, WARNING, INFO, CONFIG, FINE, FINER và FINEST. Trong nhiều ứng dụng dùng SLF4J, tên mức thường là ERROR, WARN, INFO, DEBUG, TRACE; đây là hai hệ mức của các API khác nhau, không nên giả định chúng hoàn toàn tương đương trong mọi cấu hình.

| Ý định | JUL thường dùng | Cách dùng |
| --- | --- | --- |
| Lỗi khiến thao tác thất bại nghiêm trọng | SEVERE | Lỗi không xử lý được hoặc mất khả năng phục vụ |
| Bất thường, khả năng suy giảm, retry đáng chú ý | WARNING | Phụ thuộc chậm, retry nhiều, cơ chế dự phòng được kích hoạt |
| Mốc xử lý/nghiệp vụ có ích cho vận hành | INFO | Khởi động, chấp nhận/từ chối nghiệp vụ, hoàn thành tác vụ |
| Cấu hình lúc khởi động | CONFIG | Giá trị cấu hình không nhạy cảm khi thực sự cần |
| Chẩn đoán chi tiết | FINE/FINER/FINEST | Các bước bên trong, thường tắt ở môi trường production |

**Hai nơi cùng lọc:** Trong JUL, cả Logger lẫn Handler đều có level. Chẳng hạn Logger cho phép FINE nhưng ConsoleHandler vẫn ở INFO thì thông điệp FINE sẽ không hiển thị. Ở production cần cấu hình mức log theo môi trường, nhu cầu điều tra và lưu lượng; tránh bật log quá chi tiết vô thời hạn.

## 5. Theo dõi một luồng xử lý đầu-cuối

Ví dụ luồng nhận đơn hàng:

~~~text
HTTP POST /orders
   |
   +-- request.received         [requestId=req-a1]
   |
   +-- validate quantity
   |      +-- không hợp lệ -> order.rejected [reasonCode=INVALID_QUANTITY]
   |
   +-- inventory.reserve
   |      +-- lỗi tạm thời -> inventory.retrying [attempt=2]
   |
   +-- order.persist
   |      +-- lỗi thật -> order.persist.failed [errorCode=STORAGE_ERROR]
   |
   +-- order.accepted           [outcome=SUCCESS]
   |
   +-- request.completed        [status=201, durationMs=...]
~~~

Đây là **các nhánh minh họa**: không phải một yêu cầu nhất thiết sinh ra mọi sự kiện. Với một yêu cầu thành công, chuỗi có thể gồm received → accepted → completed. Với dữ liệu sai, chuỗi có thể là received → rejected → completed với HTTP 4xx. Với lỗi cơ sở dữ liệu, log cần cho biết bước thất bại và kết quả xử lý ở biên HTTP.

Các điểm ghi thường nằm ở API/controller (vào/ra), service (quyết định nghiệp vụ), adapter/repository (lỗi giao tiếp với phụ thuộc) và job/consumer (bắt đầu/kết thúc công việc). Tránh để mọi lớp cùng ghi **một lỗi với stack trace giống nhau**, vì khiến việc đếm sự cố và đọc timeline trở nên sai lệch. Chọn nơi có đủ ngữ cảnh và trách nhiệm xử lý để ghi lỗi chính; nếu rethrow, các lớp trên chỉ thêm log khi cung cấp thông tin mới và thực sự cần.

## 6. Ví dụ Java 17+ chạy độc lập với java.util.logging

Ví dụ sau mô phỏng hai yêu cầu xử lý đơn hàng: một yêu cầu hợp lệ và một yêu cầu có số lượng không hợp lệ. Mỗi log có tên sự kiện, requestId và orderId; không ghi dữ liệu người dùng nhạy cảm.

Lưu thành tệp **SystemBehaviorLogDemo.java**:

~~~java
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class SystemBehaviorLogDemo {
    private static final Logger LOG =
            Logger.getLogger(SystemBehaviorLogDemo.class.getName());

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        Handler handler = new StreamHandler(
                System.out,
                new Formatter() {
                    @Override
                    public String format(LogRecord record) {
                        return record.getLevel().getName() + " | "
                                + record.getMessage() + System.lineSeparator();
                    }
                }) {
            @Override
            public synchronized void publish(LogRecord record) {
                super.publish(record);
                flush();
            }
        };
        handler.setLevel(Level.INFO);
        LOG.addHandler(handler);

        processOrder("req-a1", "ord-101", 2);
        processOrder("req-b2", "ord-102", 0);
    }

    private static void processOrder(String requestId,
                                     String orderId,
                                     int quantity) {
        LOG.info(() -> "event=order.received requestId=" + requestId
                + " orderId=" + orderId);

        if (quantity <= 0) {
            LOG.info(() -> "event=order.rejected requestId=" + requestId
                    + " orderId=" + orderId
                    + " outcome=REJECTED reasonCode=INVALID_QUANTITY");
            return;
        }

        LOG.info(() -> "event=order.accepted requestId=" + requestId
                + " orderId=" + orderId + " outcome=SUCCESS");
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac SystemBehaviorLogDemo.java
java SystemBehaviorLogDemo
~~~

**Đầu ra chuẩn (stdout)** của chương trình này, theo thứ tự:

~~~text
INFO | event=order.received requestId=req-a1 orderId=ord-101
INFO | event=order.accepted requestId=req-a1 orderId=ord-101 outcome=SUCCESS
INFO | event=order.received requestId=req-b2 orderId=ord-102
INFO | event=order.rejected requestId=req-b2 orderId=ord-102 outcome=REJECTED reasonCode=INVALID_QUANTITY
~~~

Giải thích các lựa chọn trong ví dụ:

1. Logger là nguồn phát sinh sự kiện; Handler chuyển log thành đầu ra; Formatter quyết định cách trình bày.
2. **setUseParentHandlers(false)** ngăn handler mặc định của logger cha ghi trùng. StreamHandler được cấu hình ghi ra stdout để có đầu ra xác định khi học tập; ConsoleHandler mặc định thường ghi ra stderr và dùng định dạng khác.
3. Override **publish()** để gọi **flush()** sau mỗi bản ghi. StreamHandler thông thường có thể giữ đệm, nên không thể mặc nhiên kỳ vọng nhìn thấy mỗi log ngay.
4. Hai lệnh **setLevel(Level.INFO)** điều khiển ngưỡng ở cả Logger và Handler.
5. Dùng **LOG.info(() -> ...)** để tạo thông điệp theo Supplier. Khi mức INFO bị vô hiệu, phần tạo chuỗi trong lambda không cần được đánh giá.
6. Sự kiện từ chối do quy tắc đầu vào là INFO vì đây là kết quả nghiệp vụ bình thường. Có thể dùng WARNING cho bất thường thật sự (ví dụ phụ thuộc suy giảm), không nên nâng mức chỉ vì nhánh xử lý trả kết quả thất bại.
7. Định dạng key=value phục vụ học tập. Trong hệ thống thực, nên có timestamp UTC, tên service, thread/trace context và hệ thống xử lý log tập trung. Nếu giá trị có khoảng trắng/ký tự đặc biệt, cần encoder hoặc format có escaping rõ ràng.

## 7. Ghi lỗi và stack trace đúng chỗ

Khi bắt lỗi bất ngờ, chỉ ghi thông điệp lỗi không đủ để tìm nguyên nhân. JUL hỗ trợ ghi ngoại lệ kèm stack trace:

~~~java
// Đoạn minh họa đặt bên trong một hàm có sẵn biến requestId
// và ngoại lệ exception; không phải chương trình độc lập.
LOG.log(
        Level.SEVERE,
        "event=order.persist.failed requestId=" + requestId
                + " errorCode=STORAGE_ERROR",
        exception);
~~~

Điểm khác biệt: tham số Throwable được truyền vào API logging, cho phép handler/formatter phù hợp trình bày stack trace. Formatter trong ví dụ chạy độc lập ở mục 6 **chỉ hiển thị level và message**, nên muốn in stack trace cần dùng formatter có hỗ trợ throwable hoặc bổ sung phần xử lý ngoại lệ vào Formatter. Cũng cần chọn mức log theo mức độ ảnh hưởng thực tế, không mặc định mọi ngoại lệ đều là SEVERE.

**Phân biệt kết quả nghiệp vụ và lỗi kỹ thuật:** dữ liệu không hợp lệ có thể tạo order.rejected với reasonCode; mất kết nối kho dữ liệu có thể tạo order.persist.failed với exception và tác động đến yêu cầu. Không biến expected exception thành sự cố nghiêm trọng chỉ vì nó được biểu diễn bằng một lớp Exception.

Khi retry, ghi **số lần thử** và **điểm kết thúc**: ví dụ inventory.retrying attempt=2 và inventory.reserve.failed khi hết khả năng thử lại. Tránh log một stack trace đầy đủ tại mọi lần retry nếu cùng một nguyên nhân; điều đó có thể tạo hàng trăm log lặp, làm che mất lỗi chính.

## 8. Liên kết log trong xử lý đồng thời và đa dịch vụ

Ở ứng dụng web, thread pool và luồng bất đồng bộ làm cho log nhiều yêu cầu xen kẽ. Chỉ dựa vào tên thread hoặc thứ tự dòng không đủ để xác định một yêu cầu. Dùng requestId/correlationId chung cho các bước liên quan.

- Ở biên HTTP, tạo hoặc tiếp nhận một requestId đáng tin cậy; kiểm tra định dạng/độ dài ID từ client, tránh lấy header tùy ý làm dữ liệu log chưa xử lý.
- Truyền requestId qua service và repository. Ví dụ mục 6 truyền tường minh qua tham số, dễ hiểu và không phụ thuộc trạng thái thread.
- Khi gọi dịch vụ khác, truyền context qua header theo quy ước hệ thống và đảm bảo dịch vụ nhận liên kết được requestId hoặc traceId.
- Với executor, CompletableFuture, virtual thread hoặc luồng không đồng bộ, phải truyền context đúng cách. **ThreadLocal/MDC không tự động truyền qua mọi ranh giới bất đồng bộ**; khi có dùng thread pool, cần dọn context sau yêu cầu để tránh rò sang yêu cầu khác.
- Nếu dùng OpenTelemetry hoặc thư viện tracing, traceId/spanId giúp liên kết log với span. JUL đơn thuần không tự sinh traceId, spanId hoặc cơ chế truyền context phân tán.

Đối với tác vụ chạy nền không gắn trực tiếp với HTTP, có thể dùng jobId hoặc messageId (đã được kiểm soát) làm correlation ID. Các mã này nên nhất quán giữa log bắt đầu, retry, hoàn thành và thất bại.

## 9. Thu thập, truy vấn và vận hành log

Đường đi điển hình: **Java Logger → Handler/Appender → console/file → agent/collector → hệ thống lưu trữ và tìm kiếm → dashboard/cảnh báo**. Tên gọi Handler thuộc JUL, Appender thường gặp ở Logback/Log4j; triển khai cụ thể phụ thuộc stack. Trong môi trường container, gửi log ra stdout/stderr rồi để nền tảng thu thập là một mẫu phổ biến, nhưng cần cấu hình encoding, rotation/retention và luồng log phù hợp.

Ví dụ các câu hỏi điều tra:

- Lọc event=order.rejected theo reasonCode=INVALID_QUANTITY để nhận biết dạng từ chối.
- Lọc requestId=req-a1 để xem chuỗi sự kiện của một yêu cầu.
- Tìm event=inventory.retrying trong 15 phút gần đây để đánh giá sự suy giảm phụ thuộc.
- Tổng hợp durationMs của request.completed để tìm đường xử lý chậm; metric/histogram thường thích hợp hơn log khi đo độ trễ liên tục và tạo SLO.

Log giúp giải thích **diễn biến cụ thể**, metric giúp nhận biết **xu hướng/tỷ lệ**, tracing giúp nhìn **đường đi và thời gian giữa các thành phần**. Không đặt toàn bộ nhu cầu quan sát hệ thống lên logging. Với yêu cầu kiểm toán có tính pháp lý hoặc chống sửa đổi, cần thiết kế **audit log riêng** với phân quyền, toàn vẹn, retention và quy định truy cập; application log thông thường không mặc nhiên đáp ứng tiêu chuẩn audit.

Trong production nên quy định: ai được đọc log, lưu bao lâu, có lọc dữ liệu nhạy cảm trước lưu không, cảnh báo dựa trên tín hiệu nào và cách xóa khi hết hạn. Cần kiểm soát dung lượng ghi, cardinality của các nhãn, chi phí ingest, độ trễ và nguy cơ nghẽn I/O. Logging bất đồng bộ có thể giảm chờ đợi của luồng nghiệp vụ nhưng có thể mất bản ghi khi dừng đột ngột; logging đồng bộ cũng có chi phí và rủi ro chặn luồng nếu đầu ra chậm.

## 10. Những lỗi thường gặp và cách sửa

| Lỗi | Hệ quả | Cách làm phù hợp |
| --- | --- | --- |
| Chỉ ghi "start"/"error"/"done" | Không xác định được hành động, đối tượng, lý do | Dùng event có tên rõ và reasonCode |
| Bỏ requestId | Không nối được các bước giữa luồng thực thi xen kẽ | Truyền correlation ID qua ranh giới phù hợp |
| Ghi INFO quá nhiều trong vòng lặp | Ngập log, tốn lưu trữ, chậm hệ thống | Chuyển sang FINE/DEBUG, gộp số liệu, lấy mẫu có chủ đích |
| Ghi bí mật hoặc toàn bộ request/response | Rò rỉ dữ liệu | Chỉ ghi trường cần thiết; che/lọc dữ liệu |
| Ghi cùng stack trace ở nhiều tầng | Đếm sai số lỗi, nhiễu khi tìm kiếm | Chọn vị trí ghi lỗi có đủ ngữ cảnh |
| Bắt ngoại lệ rồi chỉ ghi log, bỏ qua thất bại | Mất ngữ nghĩa và trạng thái lỗi | Xử lý hoặc truyền lỗi theo hợp đồng API |
| Ghi message thay đổi tùy ý, không có mã sự kiện | Khó tổng hợp, dashboard dễ vỡ | Dùng event và reasonCode ổn định |
| Bỏ qua cấu hình Logger/Handler | Log FINE không hiện, hoặc log bị trùng | Cấu hình và thử đúng các ngưỡng |
| Lấy thứ tự log làm thứ tự toàn hệ thống | Sai trong môi trường phân tán | Dùng ID liên kết, timestamp và tracing; hiểu giới hạn đồng hồ |
| Không có chính sách retention, truy cập, cảnh báo | Tăng chi phí và rủi ro, khó phản ứng sự cố | Có chính sách vận hành và mục tiêu quan sát rõ |

## 11. Checklist áp dụng cho một hành vi mới

1. Xác định **điểm bắt đầu, các quyết định, kết quả cuối** và lỗi đáng quan tâm.
2. Chọn tập event nhỏ, tên ổn định, lý do bằng reasonCode; không biến mọi bước thành INFO.
3. Quy định các trường ngữ cảnh (requestId/jobId, đối tượng, outcome, durationMs) và loại bỏ dữ liệu nhạy cảm.
4. Chọn level dựa trên tác động thực tế; phân biệt từ chối hợp lệ với lỗi kỹ thuật.
5. Ghi lỗi bất ngờ kèm throwable ở nơi có đủ ngữ cảnh, tránh nhân đôi lỗi giữa các tầng.
6. Kiểm tra trong tình huống **thành công, dữ liệu bị từ chối, phụ thuộc lỗi và nhiều yêu cầu đồng thời**: mỗi luồng có thể truy vết được, đầu ra không lộ dữ liệu, log không bị trùng hoặc thất lạc bất thường.
7. Thử cấu hình production (Logger, Handler/Appender, collector, quyền đọc, retention, cảnh báo), vì thấy log ở máy phát triển chưa bảo đảm hệ thống thu thập được nó.

**Kết quả mong muốn:** Từ những bản ghi được lưu, người vận hành có thể dựng lại những mốc quan trọng của một yêu cầu, giải thích kết quả và khoanh vùng thành phần có vấn đề. Đó là giá trị cốt lõi của việc ghi nhận hành vi hệ thống bằng Java Logging.
