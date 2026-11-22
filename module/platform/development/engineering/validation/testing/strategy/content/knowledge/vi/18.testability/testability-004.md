# Bổ sung log, chỉ số và định danh tương quan phục vụ chẩn đoán

Một hệ thống có thể xử lý đúng ở môi trường phát triển nhưng khó kiểm tra và sửa lỗi khi chạy trong môi trường tích hợp hoặc production nếu không để lại đủ dấu vết. Người dùng chỉ thấy một thông báo lỗi chung; log không cho biết yêu cầu thuộc phiên nào; các dịch vụ dùng tên giao dịch khác nhau; dashboard chỉ có CPU và bộ nhớ; nhóm vận hành không thể xác định yêu cầu đã đi qua những thành phần nào. Khi đó, việc tái hiện lỗi và tìm nguyên nhân phụ thuộc nhiều vào phỏng đoán.

Khả năng chẩn đoán cần được thiết kế cùng với chức năng. **Log** ghi lại sự kiện có ý nghĩa, **metrics** cho biết xu hướng và mức độ hoạt động, còn **định danh tương quan và trace** giúp liên kết các bước xử lý của cùng một yêu cầu xuyên qua nhiều thành phần. Khi các tín hiệu này được chuẩn hóa và truyền đúng cách, nhóm có thể trả lời hệ thống đã làm gì, việc đó xảy ra khi nào, ảnh hưởng đến bao nhiêu yêu cầu và lỗi xuất hiện ở đâu.

Trong module VALIDATION_TESTING_STRATEGY, việc bổ sung các tín hiệu chẩn đoán còn giúp kiểm thử có thể xác minh hành vi trong môi trường thực tế. Một test không chỉ kiểm tra kết quả trả về mà còn có thể xác minh rằng giao dịch được ghi nhận, metric được cập nhật và ngữ cảnh tương quan được giữ qua các dịch vụ hoặc tác vụ bất đồng bộ.

## 1. Khả năng chẩn đoán và khả năng kiểm thử

Khả năng chẩn đoán là mức độ hệ thống cung cấp thông tin đủ tin cậy để người phát triển, tester và người vận hành hiểu trạng thái và nguyên nhân của hành vi. Một hệ thống dễ chẩn đoán thường có:

- Sự kiện được ghi nhận có cấu trúc và có ý nghĩa.
- Chỉ số phản ánh tình trạng dịch vụ và hành trình quan trọng.
- Định danh giúp liên kết request, job, message và trace.
- Ngữ cảnh được truyền xuyên qua các ranh giới đồng bộ và bất đồng bộ.
- Bằng chứng có thể tìm kiếm, lọc, tổng hợp và truy vết.
- Chính sách bảo vệ dữ liệu nhạy cảm và kiểm soát chi phí lưu trữ.

Khả năng chẩn đoán hỗ trợ khả năng kiểm thử theo nhiều cách:

1. Tester có thể xác nhận hệ thống đã thực hiện hành động cần thiết, kể cả khi hành động đó diễn ra ở dịch vụ nền.
2. Khi kiểm thử thất bại, log và trace giúp tìm bước gây lỗi mà không phải đọc toàn bộ log rời rạc.
3. Metrics cho biết lỗi có ảnh hưởng đến một trường hợp riêng lẻ hay đang xảy ra trên diện rộng.
4. Định danh tương quan cho phép nối bằng chứng từ API gateway, dịch vụ nghiệp vụ, cơ sở dữ liệu, message broker và nhà cung cấp.
5. Kiểm thử khả năng phục hồi có thể xác minh rằng hệ thống ghi nhận lỗi, retry hoặc hoàn tất xử lý theo chính sách.

Không nên đồng nhất khả năng chẩn đoán với việc ghi càng nhiều log càng tốt. Quá nhiều thông tin trùng lặp, thiếu cấu trúc hoặc chứa dữ liệu nhạy cảm làm tăng chi phí và khiến tín hiệu quan trọng khó tìm hơn.

## 2. Ba nhóm tín hiệu chính

| Tín hiệu | Trả lời câu hỏi | Đơn vị thông tin thường gặp | Cách sử dụng |
|---|---|---|---|
| Log | Điều gì đã xảy ra trong một sự kiện cụ thể? | Bản ghi sự kiện có thời điểm, mức độ và trường dữ liệu | Điều tra một request, lỗi hoặc thay đổi trạng thái |
| Metrics | Hệ thống đang hoạt động ra sao theo thời gian? | Counter, gauge, histogram, timer | Dashboard, cảnh báo, SLI/SLO và phát hiện xu hướng |
| Trace | Một thao tác đi qua những thành phần nào và mất thời gian ở đâu? | Trace, span, parent/child relationship | Tìm nút thắt và lỗi xuyên dịch vụ |

Định danh tương quan không phải một nhóm tín hiệu độc lập. Nó là thông tin giúp liên kết log, metrics có nhãn phù hợp và trace với cùng một request hoặc quy trình.

### 2.1. Log

Log là bản ghi về một sự kiện đã xảy ra. Một log có ích cần cho biết:

- Thời điểm sự kiện.
- Dịch vụ hoặc thành phần phát sinh.
- Mức độ nghiêm trọng.
- Tên sự kiện hoặc thông điệp rõ ràng.
- Ngữ cảnh như request ID, correlation ID, trace ID hoặc mã nghiệp vụ phù hợp.
- Kết quả, trạng thái hoặc nguyên nhân lỗi.

Ví dụ, thông điệp "Something went wrong" rất khó điều tra. Một sự kiện payment.authorization.failed có các trường order_id, payment_attempt, failure_category, service, trace_id và correlation_id cung cấp nhiều thông tin hơn mà không cần ghi toàn bộ nội dung thanh toán.

### 2.2. Metrics

Metrics là các phép đo được thu thập theo thời gian. Chúng thường được tổng hợp và dùng để theo dõi tình trạng hệ thống:

- Số request thành công và thất bại.
- Thời gian xử lý request.
- Số job đang chờ hoặc đang chạy.
- Tỷ lệ retry.
- Số kết nối đang được sử dụng.
- Mức tiêu thụ CPU, bộ nhớ hoặc dung lượng.

Metrics giúp nhận ra xu hướng và mức độ ảnh hưởng. Một log có thể cho biết một request bị timeout; metric về tỷ lệ timeout cho biết vấn đề có đang tăng trên toàn dịch vụ hay không.

### 2.3. Trace và span

Trace mô tả hành trình xử lý của một thao tác xuyên qua nhiều thành phần. Một trace gồm các span; mỗi span đại diện cho một đơn vị công việc như nhận HTTP request, gọi dịch vụ thanh toán, truy vấn cơ sở dữ liệu hoặc xử lý message.

Span thường có:

- Tên thao tác.
- Thời điểm bắt đầu và thời lượng.
- Trace ID và Span ID.
- Quan hệ cha/con hoặc liên kết với span khác.
- Thuộc tính mô tả thành phần, loại thao tác và kết quả.
- Sự kiện hoặc thông tin lỗi cần thiết.

Trace giúp tìm bước chậm, nơi phát sinh lỗi hoặc một lần bàn giao bị thiếu. Một trace có thể liên kết với nhiều log thông qua trace ID và span ID.

## 3. Thiết kế log có cấu trúc

### 3.1. Dùng cấu trúc nhất quán

Log có cấu trúc lưu dữ liệu theo các trường riêng thay vì chỉ ghép mọi thứ thành một câu văn tự do. Định dạng JSON thường được dùng vì có thể phân tích, lọc và tổng hợp tự động.

Ví dụ một sự kiện:

~~~json
{
  "timestamp": "2026-11-16T07:30:15.482Z",
  "level": "ERROR",
  "service": "order-service",
  "event": "payment.authorization.failed",
  "environment": "staging",
  "service_version": "2.8.1",
  "request_id": "req-7f31",
  "correlation_id": "checkout-4a92",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "order_id": "order-8451",
  "failure_category": "PROVIDER_TIMEOUT",
  "retryable": true
}
~~~

Đây là dữ liệu minh họa. Trong hệ thống thật, định dạng và tên trường cần được thống nhất giữa các dịch vụ. Trường có giá trị không biết nên được xử lý nhất quán: bỏ qua, ghi null hoặc dùng trạng thái riêng theo schema đã chọn.

### 3.2. Chọn các trường quan trọng

Một schema log dùng chung có thể gồm:

| Trường | Mục đích |
|---|---|
| timestamp | Sắp xếp sự kiện theo thời gian; ưu tiên thời gian chuẩn hóa có múi giờ |
| level | Phân loại mức độ như DEBUG, INFO, WARN, ERROR |
| service | Xác định dịch vụ phát sinh |
| environment | Phân biệt development, test, staging và production |
| service_version | Liên kết sự kiện với phiên bản đang chạy |
| event | Tên sự kiện ổn định, có thể tìm kiếm |
| request_id | Nhận diện một request trong một ranh giới xử lý |
| correlation_id | Liên kết nhiều thao tác thuộc cùng một quy trình |
| trace_id / span_id | Liên kết log với distributed trace |
| operation | Tên thao tác nghiệp vụ hoặc kỹ thuật |
| outcome | Kết quả như success, rejected, timeout hoặc failed |
| duration_ms | Thời lượng khi cần phân tích một thao tác |
| error_code | Mã lỗi ổn định, phù hợp với phân loại lỗi |

Không phải log nào cũng cần mọi trường. Hãy xác định schema tối thiểu chung và cho phép trường bổ sung theo từng sự kiện. Các tên trường nên nhất quán giữa ứng dụng, nền tảng thu thập và dashboard.

### 3.3. Dùng tên sự kiện ổn định

Tên sự kiện nên mô tả điều đã xảy ra, ví dụ:

- order.created
- inventory.reservation.rejected
- payment.authorization.started
- payment.authorization.succeeded
- payment.authorization.failed
- notification.delivery.retried

Tránh dùng nội dung động làm tên sự kiện, chẳng hạn ghép mã đơn hoặc thông điệp lỗi vào tên. Giá trị động nên nằm trong trường riêng để tìm kiếm và thống kê nhất quán.

### 3.4. Chọn mức log

| Mức | Mục đích | Ví dụ |
|---|---|---|
| TRACE | Chi tiết rất sâu, thường chỉ bật có chọn lọc | Theo dõi bước nội bộ trong một thuật toán |
| DEBUG | Thông tin hỗ trợ phát triển và điều tra | Giá trị cấu hình không nhạy cảm, nhánh xử lý |
| INFO | Sự kiện vận hành bình thường có ý nghĩa | Đơn được tạo, job hoàn tất |
| WARN | Tình huống bất thường nhưng có thể tiếp tục hoặc đã được xử lý | Retry do lỗi tạm thời |
| ERROR | Thao tác thất bại cần điều tra hoặc xử lý | Không thể hoàn tất thanh toán |

Mức log cần phản ánh mức độ và ý nghĩa của sự kiện, không chỉ loại exception. Một lỗi nghiệp vụ từ chối hợp lệ có thể là INFO hoặc WARN tùy chính sách; không phải mọi từ chối đều là ERROR.

### 3.5. Tránh ghi trùng và ghi quá nhiều

Một lỗi có thể được ghi ở nhiều tầng: client, gateway, service và global exception handler. Nếu mọi tầng đều ghi stack trace giống nhau, một sự cố tạo ra nhiều bản ghi trùng và khó phân biệt nguyên nhân gốc.

Nên xác định nơi chịu trách nhiệm ghi lỗi đầy đủ, các tầng khác có thể ghi sự kiện bàn giao hoặc kết quả ngắn gọn. Log cần tập trung vào thay đổi trạng thái, ranh giới tích hợp, quyết định quan trọng và lỗi có ý nghĩa.

## 4. Thiết kế metrics có thể hành động

### 4.1. Các loại metric cơ bản

| Loại | Ý nghĩa | Ví dụ |
|---|---|---|
| Counter | Giá trị chỉ tăng, dùng đếm sự kiện | Tổng request, tổng lỗi, tổng retry |
| Gauge | Giá trị có thể tăng hoặc giảm | Số job đang chờ, số kết nối đang mở |
| Histogram | Phân phối giá trị theo các khoảng | Thời gian phản hồi, kích thước payload |
| Timer | Đo thời lượng và thường kèm số lần thực hiện | Thời gian xử lý thanh toán |

Chọn loại metric theo câu hỏi cần trả lời. Counter phù hợp để tính tỷ lệ; gauge phù hợp với trạng thái tức thời; histogram hoặc timer giúp phân tích phân phối và phân vị.

### 4.2. Bộ chỉ số RED

Đối với dịch vụ nhận request, có thể dùng ba nhóm chỉ số RED:

- **Rate:** tốc độ request đến hoặc được xử lý.
- **Errors:** số lượng hoặc tỷ lệ request lỗi.
- **Duration:** thời gian xử lý request.

RED giúp theo dõi nhanh sức khỏe của một dịch vụ. Khi tỷ lệ lỗi tăng, có thể lọc theo endpoint, loại lỗi hoặc phiên bản để khoanh vùng.

### 4.3. Bộ chỉ số USE

Đối với tài nguyên hoặc thành phần hạ tầng, có thể dùng USE:

- **Utilization:** mức sử dụng tài nguyên.
- **Saturation:** mức độ hàng đợi hoặc nhu cầu vượt khả năng phục vụ.
- **Errors:** lỗi của tài nguyên hoặc thành phần.

Ví dụ với connection pool: số kết nối đang dùng phản ánh utilization; số yêu cầu chờ lấy kết nối phản ánh saturation; số lần không lấy được kết nối phản ánh errors.

### 4.4. Đặt tên và đơn vị

Tên metric cần thể hiện rõ đại lượng và đơn vị, ví dụ:

- http.server.request.duration với đơn vị giây.
- http.server.request.count hoặc counter request phù hợp quy ước nền tảng.
- payment.retry.count.
- queue.consumer.lag.
- database.connection.active.

Tên cụ thể phụ thuộc hệ thống metric và quy ước của tổ chức. Không trộn giây và mili giây trong cùng một metric; không thay đổi ý nghĩa một metric mà vẫn giữ nguyên tên.

### 4.5. Chọn nhãn có cardinality kiểm soát

Label giúp phân tách metric theo dịch vụ, route, method, status hoặc loại thao tác. Tuy nhiên, mỗi tổ hợp label có thể tạo một time series riêng. Nếu đưa user_id, order_id, email hoặc request ID vào label, số series có thể tăng rất lớn, gây tốn bộ nhớ và làm hệ thống metric quá tải.

Nhãn thường phù hợp:

- service
- environment
- http_method
- route đã chuẩn hóa
- status_class
- operation
- failure_category có tập giá trị giới hạn

Nhãn cần tránh trong phần lớn trường hợp:

- ID người dùng hoặc đơn hàng duy nhất.
- URL đầy đủ chứa path parameter động.
- Email, số điện thoại hoặc token.
- Thông điệp lỗi tự do.
- Giá trị tùy ý do người dùng nhập.

Định danh duy nhất nên nằm trong log hoặc trace để tra cứu một lần thực thi cụ thể, không nên biến thành label của metric tổng hợp.

## 5. Định danh tương quan: request ID, correlation ID và trace ID

Các định danh thường bị dùng lẫn nhau nhưng phục vụ những mục tiêu khác nhau.

| Định danh | Phạm vi thường gặp | Mục đích |
|---|---|---|
| Request ID | Một request tại một ranh giới hoặc một dịch vụ | Tra cứu log của request cụ thể |
| Correlation ID | Một quy trình hoặc giao dịch nghiệp vụ có thể gồm nhiều request | Liên kết các thao tác cùng một mục tiêu |
| Trace ID | Một distributed trace | Liên kết các span của một lần thực thi xuyên dịch vụ |
| Span ID | Một đơn vị công việc trong trace | Xác định bước cụ thể và quan hệ cha/con |
| Business ID | Đối tượng nghiệp vụ như order ID hoặc payment ID | Liên kết dữ liệu nghiệp vụ lâu dài |

Một hành trình checkout có thể tạo nhiều request và message. Mỗi request có request ID riêng; toàn bộ quy trình dùng một correlation ID; mỗi trace có trace ID; từng span có span ID; đơn hàng có order ID. Những định danh này bổ sung cho nhau.

Không nên mặc định correlation ID luôn bằng trace ID. Một quy trình nghiệp vụ dài có thể kéo qua nhiều trace do thời gian, retry hoặc tác vụ bất đồng bộ. Correlation ID có thể liên kết các trace đó nếu chính sách và ngữ cảnh nghiệp vụ yêu cầu.

### 5.1. Sinh hoặc tiếp nhận định danh

Ở điểm vào hệ thống:

1. Nếu request đến từ một hệ thống tin cậy và có correlation ID hợp lệ, có thể tiếp tục sử dụng theo hợp đồng.
2. Nếu không có, sinh một định danh mới đủ duy nhất.
3. Kiểm tra định dạng, độ dài và ký tự trước khi ghi hoặc truyền tiếp.
4. Không dùng giá trị tùy ý từ client làm dữ liệu có độ tin cậy cao.
5. Đưa định danh vào log context và phản hồi nếu hợp đồng API cho phép.

Không ghi nhận một header không giới hạn độ dài trực tiếp vào log. Giá trị đầu vào có thể bị lợi dụng để gây log injection, tăng dung lượng hoặc làm rối truy vấn.

### 5.2. Truyền định danh qua HTTP

Khi một dịch vụ gọi dịch vụ khác, cần truyền ngữ cảnh tương quan theo hợp đồng chung. Có thể dùng header riêng cho correlation ID, đồng thời dùng W3C Trace Context (traceparent và tracestate nếu có) cho distributed tracing.

Không nên tự tạo hoặc sửa traceparent tùy tiện nếu đã dùng thư viện instrumentation. Thư viện OpenTelemetry hoặc agent tương thích thường tự inject/extract trace context. Nếu phải truyền thủ công, cần tuân theo chuẩn và giữ quan hệ trace/span đúng.

### 5.3. Truyền định danh qua message queue

Với xử lý bất đồng bộ, correlation context cần được đặt trong metadata/header của message hoặc envelope theo schema đã thống nhất. Consumer đọc ngữ cảnh và gắn nó vào log, trace của tác vụ xử lý.

Ví dụ, Order Service phát message OrderCreated; Inventory Service và Notification Service xử lý sau đó. Các consumer cần giữ correlation ID hoặc business ID để nhóm vận hành tìm được toàn bộ chuỗi sự kiện thuộc cùng đơn hàng.

### 5.4. Truyền ngữ cảnh qua thread pool và tác vụ nền

Trong ứng dụng đa luồng, thread-local context như MDC có thể không tự truyền sang thread khác. Nếu không xử lý, log trong tác vụ nền có thể mất correlation ID hoặc vô tình nhận context còn sót từ tác vụ trước.

Cần dùng cơ chế context propagation của framework hoặc truyền context một cách tường minh. Khi kết thúc tác vụ, phải khôi phục hoặc xóa context để tránh rò rỉ giữa các request.

## 6. Distributed tracing và quan hệ giữa các bước

### 6.1. Tổ chức trace

Một trace có thể gồm:

~~~mermaid
flowchart TD
    A["API Gateway<br/>Span: nhận checkout"]
    B["Order Service<br/>Span: tạo đơn"]
    C["Inventory Service<br/>Span: giữ tồn kho"]
    D["Payment Service<br/>Span: yêu cầu thanh toán"]
    E["Payment Provider<br/>Span: phản hồi bên ngoài"]
    F["Notification Worker<br/>Span: gửi xác nhận"]
    A --> B
    B --> C
    B --> D --> E
    B --> F
~~~

Sơ đồ minh họa quan hệ xử lý. Trong thực tế, các nhánh có thể chạy song song và tác vụ nền có thể bắt đầu sau khi message được phát.

### 6.2. Chọn tên span và thuộc tính

Tên span nên mô tả thao tác ổn định như POST /orders, inventory.reserve hoặc payment.authorize. Tránh đưa ID duy nhất vào tên span.

Thuộc tính có thể gồm:

- Service name và service version.
- Operation hoặc route đã chuẩn hóa.
- Loại phụ thuộc như database, HTTP client hoặc message broker.
- Kết quả hoặc loại lỗi.
- Mã nghiệp vụ được phép ghi nhận theo chính sách.

Không thêm token, mật khẩu, dữ liệu thẻ hoặc nội dung nhạy cảm vào span attribute. Trace có thể được lưu và chia sẻ rộng hơn log ứng dụng, nên cần áp dụng cùng chính sách bảo vệ dữ liệu.

### 6.3. Span event và lỗi

Span event ghi nhận một sự kiện xảy ra trong thời gian span, chẳng hạn retry bắt đầu hoặc callback nhận được. Khi thao tác thất bại, ghi nhận loại lỗi và trạng thái span phù hợp. Không nên chỉ đánh dấu lỗi mà không có thông tin phân loại, nhưng cũng không nên đưa toàn bộ payload nhạy cảm vào exception hoặc event.

### 6.4. Sampling

Sampling giới hạn số trace được lưu để kiểm soát chi phí. Có thể giữ toàn bộ trace trong môi trường kiểm thử hoặc chọn mẫu phù hợp trong production. Nếu chỉ lấy mẫu ngẫu nhiên, một số lỗi hiếm có thể không có trace.

Với hệ thống cần điều tra lỗi, cân nhắc tail-based sampling hoặc chính sách ưu tiên giữ trace lỗi, thời gian chậm bất thường và hành trình quan trọng nếu nền tảng hỗ trợ. Dù vậy, sampling không nên được coi là bảo đảm mọi request đều có trace.

## 7. Ví dụ Java: gắn correlation context vào log

Với SLF4J và MDC, ứng dụng có thể đặt các trường tương quan vào context để logging backend xuất chúng cùng mỗi bản ghi. Ví dụ đơn giản:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

public final class RequestHandler {
    private static final Logger log =
        LoggerFactory.getLogger(RequestHandler.class);

    public Response handle(Request request, String correlationId) {
        MDC.put("correlation_id", correlationId);
        try {
            log.info("checkout.started");
            Response response = process(request);
            log.info("checkout.completed");
            return response;
        } catch (RuntimeException ex) {
            log.error("checkout.failed", ex);
            throw ex;
        } finally {
            MDC.remove("correlation_id");
        }
    }

    private Response process(Request request) {
        // Xử lý nghiệp vụ
        return new Response();
    }
}
~~~

Đoạn mã minh họa cách đặt và dọn context trong cùng luồng thực thi. Trong ứng dụng web thực tế, nên đặt correlation context ở filter/interceptor tại ranh giới request để áp dụng nhất quán cho mọi handler. Cần bảo đảm cleanup trong mọi nhánh, kể cả khi có exception.

Nếu dùng thread pool hoặc tác vụ bất đồng bộ, MDC không tự động được truyền an toàn trong mọi cấu hình. Dùng cơ chế context propagation tương ứng và kiểm thử trường hợp hai request chạy liên tiếp trên cùng worker thread.

## 8. Ví dụ Java: đo thời gian và số lần xử lý

Với thư viện Micrometer, có thể tạo counter và timer để theo dõi thao tác:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.concurrent.TimeUnit;

public final class PaymentMetrics {
    private final Counter authorizationFailures;
    private final Timer authorizationDuration;

    public PaymentMetrics(MeterRegistry registry) {
        this.authorizationFailures = Counter.builder(
                "payment.authorization.failures")
            .description("Số lần yêu cầu authorization thất bại")
            .register(registry);

        this.authorizationDuration = Timer.builder(
                "payment.authorization.duration")
            .description("Thời gian xử lý authorization")
            .register(registry);
    }

    public void recordFailure() {
        authorizationFailures.increment();
    }

    public void recordDuration(long durationNanos) {
        authorizationDuration.record(durationNanos, TimeUnit.NANOSECONDS);
    }
}
~~~

Ví dụ tách lớp đo lường khỏi logic nghiệp vụ. Trong triển khai thật, nên dùng timer trực tiếp quanh thao tác để tránh tự đo thời lượng không chính xác. Có thể thêm tag với tập giá trị giới hạn như provider, outcome hoặc environment; không thêm order_id hay customer_id làm tag vì cardinality có thể tăng không kiểm soát.

## 9. Ví dụ: tạo span với OpenTelemetry

API OpenTelemetry cho phép tạo span quanh một thao tác. Mã dưới đây minh họa nguyên tắc; cách khởi tạo tracer và cấu hình exporter phụ thuộc ứng dụng:

~~~java
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;

public final class PaymentService {
    private final Tracer tracer;

    public PaymentService(Tracer tracer) {
        this.tracer = tracer;
    }

    public PaymentResult authorize(PaymentRequest request) {
        Span span = tracer.spanBuilder("payment.authorize").startSpan();
        try (Scope scope = span.makeCurrent()) {
            span.setAttribute("payment.provider", request.provider());
            PaymentResult result = callProvider(request);
            span.setAttribute("payment.outcome", result.outcome());
            return result;
        } catch (RuntimeException ex) {
            span.recordException(ex);
            span.setStatus(StatusCode.ERROR);
            throw ex;
        } finally {
            span.end();
        }
    }

    private PaymentResult callProvider(PaymentRequest request) {
        // Gọi adapter của nhà cung cấp
        return PaymentResult.pending();
    }
}
~~~

Scope làm cho span hiện tại có thể được các thao tác được instrument tiếp theo nhận biết trong thời gian xử lý. Trong ứng dụng thực tế, ưu tiên instrumentation tự động cho HTTP server/client, database và framework khi phù hợp; chỉ tạo span thủ công cho thao tác nghiệp vụ mà instrumentation tự động không thể mô tả đủ.

## 10. Bảo vệ dữ liệu và độ tin cậy của tín hiệu

Log, metric và trace đều có thể làm lộ thông tin hoặc tạo chi phí nếu không được thiết kế cẩn thận.

### 10.1. Không ghi dữ liệu nhạy cảm

Không ghi trực tiếp:

- Mật khẩu, access token, refresh token hoặc API key.
- Số thẻ thanh toán, mã bảo mật hoặc dữ liệu xác thực.
- Nội dung cá nhân không cần thiết như email, số điện thoại, địa chỉ đầy đủ.
- Payload chứa bí mật hoặc dữ liệu khách hàng.
- Secret trong URL, header hoặc exception message.

Nếu cần liên kết với một đối tượng nghiệp vụ, ưu tiên mã định danh nội bộ đã được phê duyệt hoặc giá trị giả danh. Cần áp dụng che dữ liệu tại nguồn và kiểm soát quyền truy cập ở nền tảng thu thập; không chỉ dựa vào việc người dùng dashboard không mở một trường.

### 10.2. Phòng chống log injection

Giá trị từ người dùng có thể chứa ký tự xuống dòng, ký tự điều khiển hoặc nội dung giả dạng trường log. Cần dùng logging framework có encoding an toàn, giới hạn độ dài và chuẩn hóa dữ liệu đầu vào. Không nối chuỗi trực tiếp với nội dung không tin cậy theo cách có thể tạo bản ghi giả.

### 10.3. Quản lý retention và quyền truy cập

Xác định thời gian lưu log, metrics và trace theo nhu cầu điều tra, chính sách dữ liệu và chi phí. Giới hạn quyền truy cập theo vai trò, ghi nhận truy cập khi cần và có quy trình xóa dữ liệu hết hạn.

### 10.4. Hệ thống phải tiếp tục xử lý khi nền tảng telemetry lỗi

Nếu log exporter hoặc telemetry backend tạm thời không sẵn sàng, ứng dụng không nên thất bại toàn bộ nghiệp vụ chỉ vì không gửi được một bản ghi chẩn đoán, trừ khi đó là yêu cầu kiểm soát đặc biệt đã được xác định. Cần cấu hình buffer, timeout, retry và giới hạn tài nguyên để telemetry không gây nghẽn hoặc làm tăng độ trễ ngoài kiểm soát.

### 10.5. Đồng bộ thời gian

Timestamp từ nhiều máy cần có đồng hồ được đồng bộ đủ tốt để sắp xếp sự kiện. Dùng thời gian chuẩn có múi giờ, thường là UTC, và theo dõi clock skew. Trace có thể cung cấp quan hệ cha/con, nhưng timestamp lệch vẫn làm khó phân tích thời lượng và thứ tự sự kiện.

## 11. Kiểm thử các tín hiệu chẩn đoán

Không nên chỉ triển khai instrumentation rồi giả định nó hoạt động. Cần kiểm thử cả nội dung, ngữ cảnh và hành vi khi telemetry không sẵn sàng.

### 11.1. Kiểm thử log

- Xác minh sự kiện quan trọng được ghi ở đúng mức.
- Xác minh tên sự kiện và các trường bắt buộc có mặt.
- Xác minh correlation ID và trace ID được gắn đúng.
- Xác minh lỗi có mã phân loại và stack trace ở nơi phù hợp.
- Xác minh secret và dữ liệu nhạy cảm không xuất hiện.
- Tránh assertion phụ thuộc vào toàn bộ câu chữ log nếu câu chữ không phải hợp đồng công khai.

Có thể kiểm tra các trường có cấu trúc thay vì so sánh nguyên văn cả dòng log. Cách này giúp test ít mong manh khi nhóm chỉnh sửa cách diễn đạt.

### 11.2. Kiểm thử metrics

- Xác minh counter tăng khi sự kiện tương ứng xảy ra.
- Xác minh timer ghi nhận thời lượng cho thao tác.
- Xác minh lỗi và thành công được phân loại đúng.
- Xác minh tag chỉ dùng tập giá trị có cardinality giới hạn.
- Xác minh metric không bị tăng hai lần do retry hoặc ghi nhận trùng.
- Xác minh tên và đơn vị nhất quán.

Trong unit test, có thể dùng registry trong bộ nhớ như SimpleMeterRegistry để đọc giá trị metric mà không cần kết nối backend thật.

### 11.3. Kiểm thử tương quan và trace

- Một request đi qua nhiều dịch vụ vẫn giữ correlation ID theo hợp đồng.
- Trace có cùng trace ID cho các span thuộc cùng một trace.
- Span con có quan hệ với span cha đúng.
- Message consumer nhận được context đã được inject vào message.
- Tác vụ bất đồng bộ không mất hoặc dùng nhầm context của request khác.
- Trace có trạng thái lỗi và thuộc tính cần thiết khi thao tác thất bại.

Với OpenTelemetry, có thể dùng exporter trong bộ nhớ trong kiểm thử để xác minh span được tạo và thuộc tính cần thiết được ghi. Không nên yêu cầu mọi chi tiết triển khai nội bộ phải xuất hiện trong trace nếu đó không phải mục tiêu kiểm thử.

### 11.4. Kiểm thử lỗi nền tảng telemetry

Tạo tình huống collector hoặc backend tạm thời không sẵn sàng, buffer đầy hoặc exporter timeout. Xác minh ứng dụng vẫn tuân theo chính sách đã chọn, không treo request vô hạn, không làm mất tài nguyên và có cơ chế phục hồi phù hợp.

## 12. Ví dụ xuyên suốt: chẩn đoán hành trình checkout

Giả sử khách hàng tạo đơn và thanh toán qua nhà cung cấp bên ngoài. Hành trình đi qua API Gateway, Order Service, Inventory Service, Payment Service và Notification Worker.

### 12.1. Gắn ngữ cảnh từ điểm vào

API Gateway nhận request checkout. Nếu chưa có correlation ID hợp lệ, gateway tạo ID mới; đồng thời trace instrumentation tạo hoặc tiếp tục trace context. Các định danh được đưa vào context của request và phản hồi theo hợp đồng.

### 12.2. Ghi log tại ranh giới nghiệp vụ

Order Service ghi order.created với order ID và correlation ID. Inventory Service ghi inventory.reservation.succeeded hoặc inventory.reservation.rejected. Payment Service ghi payment.authorization.started và kết quả cuối theo trạng thái nhà cung cấp.

Các dịch vụ không cần ghi toàn bộ payload. Chỉ ghi mã nghiệp vụ, kết quả, loại lỗi và trường cần thiết để điều tra.

### 12.3. Đo metrics

Nhóm theo dõi:

- Tốc độ checkout.
- Tỷ lệ checkout thất bại.
- Thời gian xử lý p50, p95 và p99.
- Tỷ lệ payment timeout.
- Số lần retry.
- Độ trễ hàng đợi của Notification Worker.

Nếu payment timeout tăng, dashboard cho thấy phạm vi và thời điểm vấn đề. Nhóm có thể chuyển sang trace để tìm nhà cung cấp hoặc bước gọi API gây chậm.

### 12.4. Truy vết một giao dịch cụ thể

Khi khách báo đơn order-8451 bị treo, người điều tra tìm order ID hoặc correlation ID trong log. Từ bản ghi tìm được, họ lấy trace ID để mở trace và thấy:

1. API Gateway nhận request.
2. Order Service tạo đơn.
3. Inventory Service giữ tồn kho thành công.
4. Payment Service gọi nhà cung cấp nhưng timeout.
5. Worker retry theo chính sách.
6. Callback thành công đến sau đó và cập nhật trạng thái.

Nếu các bước dùng ID khác nhau và không truyền context, nhóm khó biết chúng thuộc cùng một quy trình. Nếu log chỉ ghi payment failed, cũng không thể phân biệt timeout trước khi nhà cung cấp nhận yêu cầu với timeout sau khi giao dịch đã được xử lý.

### 12.5. Kiểm tra bằng test

Một integration test có thể tạo checkout với nhà cung cấp giả lập timeout, sau đó phát callback thành công. Test xác minh trạng thái đơn, số lần ghi nhận thanh toán, log sự kiện quan trọng, metric timeout/retry và correlation context trên các message. Test không cần phụ thuộc vào câu chữ log; nó kiểm tra schema và các thuộc tính chẩn đoán đã được thống nhất.

## 13. Quy trình bổ sung khả năng chẩn đoán

### Bước 1: Chọn hành trình và câu hỏi điều tra

Chọn một hành trình có rủi ro hoặc thường phát sinh lỗi. Viết ra những câu hỏi cần trả lời khi có sự cố: request đi qua đâu, bước nào thất bại, kéo dài bao lâu, ảnh hưởng bao nhiêu giao dịch và có retry hay không?

### Bước 2: Xác định các ranh giới và định danh

Liệt kê API, dịch vụ, message, job và nhà cung cấp tham gia. Xác định request ID, correlation ID, trace ID, business ID và cách truyền từng loại qua mỗi ranh giới.

### Bước 3: Chuẩn hóa schema log và metric

Chọn tên sự kiện, trường bắt buộc, mức log, tên metric, đơn vị và nhãn được phép. Ghi rõ trường nào có thể chứa dữ liệu nhạy cảm và cách loại bỏ.

### Bước 4: Instrument các điểm quan trọng

Bổ sung log tại điểm nhận request, quyết định nghiệp vụ, thay đổi trạng thái, gọi phụ thuộc, retry và hoàn tất. Thêm metric cho rate, error, duration, queue và saturation. Tạo span cho các thao tác xuyên dịch vụ hoặc có thời gian đáng kể.

### Bước 5: Truyền context xuyên suốt

Kiểm tra propagation qua HTTP, message broker, thread pool và scheduler. Bảo đảm context được khôi phục hoặc xóa đúng lúc, không rò rỉ giữa các request.

### Bước 6: Kiểm thử và quan sát

Chạy các trường hợp thành công, lỗi, timeout, retry, callback lặp và xử lý bất đồng bộ. Kiểm tra log, metrics, trace và quyền truy cập trên môi trường đại diện.

### Bước 7: Thiết lập dashboard và cảnh báo

Chọn dashboard theo câu hỏi vận hành và cảnh báo theo SLO hoặc ngưỡng có ý nghĩa. Tránh cảnh báo cho mọi lỗi đơn lẻ nếu nó không cần hành động; cảnh báo cần có người nhận, hướng điều tra và runbook phù hợp.

### Bước 8: Rà soát theo thay đổi

Khi thêm dịch vụ, đổi giao thức hoặc thay đổi hành trình, cập nhật schema, propagation và kiểm thử telemetry. Khả năng chẩn đoán là một phần của thiết kế hệ thống, cần được duy trì cùng mã nguồn.

## 14. Những sai lầm thường gặp

- **Chỉ ghi thông điệp tự do:** khó lọc và tổng hợp vì tên và cấu trúc không nhất quán.
- **Thiếu định danh chung:** log của các dịch vụ không thể liên kết thành một hành trình.
- **Dùng một ID cho mọi mục đích:** request, correlation, trace và business ID có phạm vi khác nhau.
- **Đưa ID duy nhất vào metric label:** tạo cardinality cao và làm backend metric quá tải.
- **Ghi quá nhiều dữ liệu:** làm tăng chi phí và có thể làm lộ thông tin nhạy cảm.
- **Không dọn MDC hoặc context:** request sau có thể nhận định danh của request trước khi dùng lại thread.
- **Không truyền context qua message:** trace bị đứt khi xử lý bất đồng bộ.
- **Chỉ đo trung bình:** bỏ qua tail latency và nhóm request chậm.
- **Không ghi kết quả cuối:** chỉ ghi bắt đầu mà không ghi thành công, thất bại hoặc thời lượng.
- **Lạm dụng ERROR:** lỗi nghiệp vụ dự kiến có thể tạo cảnh báo nhiễu.
- **Phụ thuộc hoàn toàn vào sampling:** trace của lỗi hiếm có thể không được lưu.
- **Để telemetry làm gián đoạn nghiệp vụ:** exporter lỗi có thể gây nghẽn nếu timeout và buffer không được kiểm soát.
- **Không kiểm thử instrumentation:** tên trường, context hoặc metric có thể sai mà test chức năng vẫn đạt.

## 15. Checklist cho log, metrics và correlation

- [ ] Mỗi dịch vụ có tên, phiên bản và môi trường được ghi nhận nhất quán.
- [ ] Log có timestamp, level, event name và các trường cần thiết.
- [ ] Tên sự kiện ổn định và không chứa giá trị động.
- [ ] Mức log phản ánh đúng ý nghĩa sự kiện.
- [ ] Log lỗi có mã phân loại và thông tin điều tra phù hợp.
- [ ] Request ID, correlation ID và trace context được phân biệt rõ.
- [ ] Định danh đầu vào được kiểm tra và giới hạn độ dài.
- [ ] Context được truyền qua HTTP, message và tác vụ nền.
- [ ] MDC hoặc context tương đương được cleanup sau khi xử lý.
- [ ] Metrics có loại, tên, đơn vị và nhãn phù hợp.
- [ ] Không dùng ID duy nhất hoặc dữ liệu cá nhân làm metric label.
- [ ] Dashboard theo dõi rate, errors, duration và tài nguyên quan trọng.
- [ ] Trace thể hiện quan hệ span và các điểm gọi phụ thuộc cần thiết.
- [ ] Sampling và retention phù hợp với nhu cầu điều tra và chi phí.
- [ ] Secret và dữ liệu nhạy cảm được loại bỏ hoặc che tại nguồn.
- [ ] Telemetry backend lỗi không gây treo hoặc làm hỏng nghiệp vụ ngoài chính sách.
- [ ] Có kiểm thử xác minh log schema, metric và context propagation.

## 16. Mối liên hệ giữa tín hiệu chẩn đoán và chất lượng kiểm thử

~~~mermaid
flowchart TD
    A["Request hoặc sự kiện nghiệp vụ"]
    B["Context: request ID, correlation ID, trace context"]
    C["Các dịch vụ và tác vụ xử lý"]
    D["Structured logs"]
    E["Metrics"]
    F["Trace và span"]
    G["Log search, dashboard và trace view"]
    H["Điều tra nguyên nhân và đánh giá ảnh hưởng"]
    I["Cải thiện test, instrumentation và hành vi"]
    A --> B --> C
    C --> D
    C --> E
    C --> F
    D --> G
    E --> G
    F --> G
    G --> H --> I
~~~

Log cho biết sự kiện cụ thể, metrics cho biết xu hướng và mức độ ảnh hưởng, còn correlation ID cùng trace giúp nối các bước xử lý thành một câu chuyện có thể điều tra. Khi các tín hiệu được chuẩn hóa, bảo vệ dữ liệu và kiểm thử định kỳ, hệ thống trở nên dễ hiểu hơn trong cả môi trường kiểm thử lẫn vận hành. Điều đó giúp nhóm tái hiện lỗi nhanh, xác định đúng ranh giới gây vấn đề và cải thiện chất lượng sản phẩm dựa trên bằng chứng.
