# Cảnh báo sự cố bằng logging trong Java

## 1. Cảnh báo sự cố là một mục tiêu của logging

**Cảnh báo sự cố (incident alerting)** là việc phát hiện dấu hiệu hệ thống đang gặp vấn đề và thông báo kịp thời cho người hoặc hệ thống chịu trách nhiệm. Logging giúp đạt mục tiêu này bằng cách lưu lại các sự kiện có ý nghĩa: yêu cầu thất bại, tài nguyên không sẵn sàng, kết nối bị ngắt, tác vụ nền lỗi, giao dịch không hoàn thành, hoặc thành phần phụ thuộc hoạt động bất thường.

Cần phân biệt ba khái niệm:

- **Log event:** Một bản ghi về điều đã xảy ra, chẳng hạn một lần gọi cơ sở dữ liệu thất bại. Sự kiện đơn lẻ chưa chắc là sự cố cần đánh thức người trực.
- **Incident:** Sự suy giảm hoặc gián đoạn thực tế của dịch vụ, tính đúng đắn dữ liệu hay chức năng quan trọng, cần được đánh giá và xử lý.
- **Alert:** Tín hiệu có chủ đích cho biết điều kiện phát hiện sự cố đã thỏa mãn, kèm mức ưu tiên, bằng chứng và thông tin để người nhận hành động.

**Ứng dụng ghi log không đồng nghĩa với việc đã có cảnh báo.** Log chỉ trở thành nguồn cảnh báo khi có quy trình thu thập, đánh giá điều kiện, gửi thông báo và xác nhận người chịu trách nhiệm. Mục tiêu là phát hiện nhanh sự cố ảnh hưởng đến người dùng hoặc hệ thống, giảm thời gian xử lý và cung cấp dữ liệu để chẩn đoán.

Ví dụ: một request HTTP trả về 500 có thể chỉ là lỗi hiếm gặp; hàng trăm request lỗi trong vài phút có thể phản ánh một sự cố đáng báo động. Ngược lại, một sự kiện duy nhất báo dữ liệu bị hỏng hoặc việc sao lưu quan trọng thất bại có thể cần cảnh báo ngay.

## 2. Các loại dấu hiệu bất thường có thể nhận biết từ log

| Dấu hiệu trong log | Ví dụ | Ý nghĩa cần kiểm tra |
| --- | --- | --- |
| Lỗi liên tục | Nhiều bản ghi về lỗi HTTP 5xx, ghi dữ liệu thất bại | Chức năng phục vụ người dùng có thể không khả dụng |
| Kết nối tới dependency lỗi | Database timeout, message broker không kết nối được | Tác động dây chuyền tới thao tác nghiệp vụ |
| Retry hết lượt hoặc circuit breaker mở | Gọi API đối tác thất bại sau chính sách retry | Hệ thống đã hết khả năng phục hồi tự động cho yêu cầu đó |
| Job định kỳ thất bại | Không tạo được báo cáo hoặc bản sao lưu | Dữ liệu hoặc tác vụ quan trọng bị chậm, mất hoặc không đầy đủ |
| Bất thường về tài nguyên | Hết dung lượng, không ghi được file | Cần đánh giá nguy cơ ngừng dịch vụ |
| Vi phạm tính toàn vẹn | Phát hiện checksum sai, trạng thái không nhất quán | Có thể cần xử lý ưu tiên cao ngay cả với một sự kiện |
| Sự kiện bảo mật có giá trị điều tra | Nhiều lần xác thực thất bại trên cùng mẫu hành vi | Cần kết hợp chính sách bảo mật và ngữ cảnh để tránh báo giả |

Log có lợi thế cho việc xác định **đã xảy ra lỗi gì, ở thành phần nào và trong ngữ cảnh nào**. Tuy nhiên, nếu tiến trình chết trước khi ghi log, đường truyền log bị gián đoạn hoặc tác vụ không phát sự kiện, việc chỉ theo dõi log có thể bỏ sót sự cố. Vì vậy hệ thống production nên kết hợp **metrics, health checks và tracing**. Chẳng hạn, tỷ lệ lỗi và độ trễ thường thích hợp để cảnh báo bằng metrics, còn log cung cấp nguyên nhân và ngữ cảnh điều tra.

## 3. Luồng từ một bản ghi Java đến cảnh báo

Một kiến trúc điển hình:

~~~text
Ứng dụng Java
  | phát sự kiện INFO / WARNING / SEVERE...
  v
Logging API + backend / handler / appender
  | stdout, file hoặc collector
  v
Bộ thu thập tập trung
  | chuẩn hóa, lọc dữ liệu nhạy cảm, thêm nhãn
  v
Kho log và công cụ tìm kiếm / phân tích
  | truy vấn theo thời gian, service, event, severity
  v
Bộ đánh giá quy tắc cảnh báo
  | ngưỡng, cửa sổ thời gian, nhóm sự kiện, điều kiện hồi phục
  v
Bộ quản lý cảnh báo
  | gộp, chống lặp, điều hướng, tạm ngưng khi bảo trì
  v
On-call / ticket / kênh vận hành
  | xác nhận, điều tra, khắc phục và đóng sự cố
~~~

Các tên công cụ cụ thể có thể khác nhau: hệ thống có thể dùng JUL, SLF4J/Logback hoặc Log4j 2 ở ứng dụng; sau đó thu thập bằng agent/collector và gửi tới nền tảng quan sát. **Nơi định nghĩa cảnh báo thường nằm ở hệ thống quan sát hoặc giám sát**, bởi nó cần đánh giá dữ liệu của nhiều instance, hoạt động ngay khi một instance chết và giữ trạng thái độc lập với tiến trình ứng dụng.

Mỗi mắt xích cần được giám sát: log có thể đến chậm, bị mất, vượt hạn mức thu thập hoặc bị giảm mẫu. Một cảnh báo dựa trên “không thấy log” chỉ đáng tin khi biết rõ tần suất sự kiện dự kiến và tình trạng pipeline thu thập.

## 4. Ghi sự kiện đủ thông tin để phát hiện và điều tra

Một log phục vụ cảnh báo nên chứa các trường có cấu trúc, nhất quán:

| Trường | Mục đích |
| --- | --- |
| **timestamp** | Xác định thời điểm xảy ra sự kiện, ưu tiên ISO 8601 có múi giờ, thường là UTC |
| **level** | Mức độ nghiêm trọng hoặc chi tiết theo logging framework |
| **service, environment** | Xác định dịch vụ và môi trường như production, staging |
| **event_code** | Mã sự kiện ổn định, ví dụ PAYMENT_PROVIDER_UNAVAILABLE; đáng tin hơn phân tích câu chữ |
| **outcome, status** | Thành công/thất bại; HTTP status hoặc mã lỗi nghiệp vụ khi thích hợp |
| **trace_id, request_id** | Nối các log liên quan đến một yêu cầu hoặc chuỗi lời gọi |
| **dependency, operation** | Xác định đối tượng và thao tác đang gặp vấn đề |
| **error_type, exception** | Phân loại lỗi và giữ stack trace ở nơi phù hợp |
| **version, instance** | Liên hệ sự cố với bản phát hành hay instance cụ thể |

Ví dụ hai sự kiện JSON minh họa:

~~~json
{
  "timestamp": "2026-11-09T10:00:00Z",
  "level": "SEVERE",
  "service": "payment-service",
  "environment": "production",
  "event_code": "PAYMENT_PROVIDER_UNAVAILABLE",
  "operation": "authorize",
  "dependency": "payment-gateway",
  "request_id": "req-42",
  "error_type": "TimeoutException",
  "message": "Provider did not respond within timeout"
}
~~~

~~~json
{
  "timestamp": "2026-11-09T10:00:10Z",
  "level": "INFO",
  "service": "payment-service",
  "environment": "production",
  "event_code": "PAYMENT_RECOVERED",
  "operation": "authorize",
  "request_id": "req-43",
  "message": "Subsequent operation completed"
}
~~~

Đây là **mẫu cấu trúc log**, không phải dạng xuất JSON mặc định của **java.util.logging**. Nếu dùng JUL, phải chọn Formatter/Handler phù hợp hoặc chuyển qua hệ thống logging có hỗ trợ định dạng có cấu trúc. Nếu định dạng chỉ là chuỗi tự do và thay đổi thường xuyên, quy tắc cảnh báo theo nội dung thông báo sẽ dễ hỏng.

**Không ghi mật khẩu, access token, khóa bí mật, dữ liệu thanh toán, thông tin cá nhân nhạy cảm hoặc toàn bộ payload bí mật.** Khi cần liên kết sự kiện, dùng ID kỹ thuật được kiểm soát quyền truy cập; giới hạn thời gian lưu và người được xem. Tránh đưa **request_id** hoặc **user_id** vào khóa nhóm của cảnh báo: số lượng giá trị lớn khiến mỗi lỗi thành một nhóm riêng và tạo bão thông báo.

## 5. Xây dựng quy tắc cảnh báo hữu ích

Một cảnh báo cần xác định rõ **tín hiệu, điều kiện kích hoạt, phạm vi áp dụng, độ ưu tiên, cách khôi phục và nơi tiếp nhận**. Có thể đi từ những câu hỏi sau:

1. **Sự cố nào muốn phát hiện?** Ví dụ lỗi thanh toán thực sự làm đơn hàng không hoàn tất, thay vì mọi exception đã được xử lý thành công.
2. **Tín hiệu nào có thể đo được?** Đếm mã sự kiện ổn định, tỷ lệ HTTP 5xx, kết quả job hoặc metric phản ánh tác động.
3. **Trong khoảng thời gian nào?** Chẳng hạn cửa sổ trượt 5 phút; phải nêu rõ cách xử lý sự kiện đến muộn.
4. **Khi nào kích hoạt?** Ngưỡng số lượng, tỷ lệ, mức độ ảnh hưởng và số lần đánh giá liên tiếp.
5. **Nhóm theo gì?** Thường theo **service, environment** và loại lỗi; thêm nhãn khi nhóm đó cần người xử lý riêng.
6. **Khi nào hết cảnh báo?** Có điều kiện hồi phục rõ ràng, tránh bật/tắt liên tục khi chỉ số dao động quanh ngưỡng.
7. **Ai nhận, cần làm gì?** Chỉ định nhóm trực, mức khẩn cấp và đường dẫn tới dashboard/runbook.

Ví dụ quy tắc **tỷ lệ HTTP 5xx**:

~~~text
Nguồn: một sự kiện http_response cho mỗi yêu cầu đã hoàn tất
Phạm vi: service=checkout, environment=production
Cửa sổ: 5 phút gần nhất
Mẫu số: tổng số http_response trong cửa sổ
Tử số: số http_response có status từ 500 đến 599

Kích hoạt nếu:
  tổng yêu cầu >= 200
  và (số 5xx / tổng yêu cầu) >= 0.05
  trong 2 lần đánh giá liên tiếp, mỗi lần cách nhau 1 phút

Khôi phục nếu:
  tổng yêu cầu >= 200
  và tỷ lệ 5xx < 0.02
  ổn định trong 10 phút

Nhóm cảnh báo: service + environment
~~~

Các con số trên là **ví dụ để học cách thiết kế**, không phải SLO hay ngưỡng mặc định cho mọi ứng dụng. Với lưu lượng thấp, dùng tỷ lệ đơn lẻ dễ báo giả (1 lỗi trên 2 yêu cầu là 50%). Với lỗi cực kỳ nghiêm trọng như mất dữ liệu, một sự kiện xác thực có thể cần báo ngay. Cần phân biệt việc gọi lại API thất bại nhiều lần với số thao tác nghiệp vụ thực sự thất bại: đếm cả các lần retry có thể phóng đại tác động.

**Mức log khác mức ưu tiên cảnh báo.** Một bản ghi SEVERE/ERROR chưa chắc phải paging ngay; nhiều lỗi nhỏ có thể đã được tự phục hồi. Trong khi đó, một bản ghi WARNING về việc sao lưu quan trọng không còn hoạt động có thể cần cảnh báo mức cao nếu thời hạn khôi phục dữ liệu bị đe dọa. Mức ưu tiên của alert phải dựa trên tác động, mức khẩn cấp, khả năng hành động và chính sách vận hành.

## 6. Cửa sổ thời gian, chống trùng và chống báo giả

### Đếm theo cửa sổ thời gian

Không nên gửi cảnh báo chỉ vì mỗi lần phát hiện một log lỗi. Thay vào đó, theo dõi số lỗi hoặc tỷ lệ lỗi trong một **cửa sổ thời gian** (ví dụ 3 lỗi trong 60 giây). Cửa sổ trượt cập nhật theo thời điểm đánh giá; cửa sổ cố định có các khoảng biên cố định và có thể chia tách một đợt lỗi qua hai khoảng.

Đếm sự kiện cần dựa trên thời điểm phù hợp, xử lý trùng lặp do retry thu thập và hiểu sai lệch giữa **event time** (thời điểm xảy ra) với **ingestion time** (thời điểm log đến hệ thống). Với hệ thống phân tán, đồng bộ đồng hồ và chính sách xử lý log đến muộn rất quan trọng.

### Chống lặp và gộp cảnh báo

Nếu một lỗi tồn tại 20 phút, quy tắc có thể tiếp tục thỏa ngưỡng mỗi phút. Hệ thống nên giữ **một incident đang mở** với cập nhật trạng thái, thay vì tạo một sự cố hoặc gửi thông báo mới ở mọi chu kỳ. Có thể gộp nhiều sự kiện cùng service và loại nguyên nhân; tách những dịch vụ hoặc khu vực có người xử lý khác nhau.

Khi một lỗi ở dependency gây hàng loạt triệu chứng phía sau, correlation/grouping giúp thấy sự cố gốc; nhưng không được tự động khẳng định mọi triệu chứng đều có cùng nguyên nhân chỉ vì cùng thời điểm.

### Điều kiện hồi phục

Nên có **điều kiện đóng cảnh báo** khác với ngưỡng mở, chẳng hạn kích hoạt khi lỗi trên 5% và chỉ đóng khi dưới 2% trong 10 phút. Khoảng cách này gọi là **hysteresis** và giúp tránh trạng thái liên tục bật/tắt. Phục hồi có thể yêu cầu dịch vụ thực sự xử lý thành công request mới, thay vì chỉ “không còn log lỗi” khi lưu lượng đã về 0.

### Giảm nhiễu có chủ đích

- Tạm ngưng thông báo khi có bảo trì được phê duyệt, nhưng tiếp tục ghi dữ liệu để điều tra.
- Phân biệt staging/test với production để không gọi nhầm người trực.
- Điều chỉnh ngưỡng theo lưu lượng và mức quan trọng của tính năng.
- Không dùng một log từ các vòng retry đã được xử lý làm bằng chứng duy nhất của outage.
- Có **dead-man/heartbeat hoặc synthetic check** khi dịch vụ được mong đợi phải liên tục hoạt động; đừng mặc định việc không có log nghĩa là khỏe mạnh.

## 7. Ví dụ Java 17: phát hiện sự cố từ các bản ghi SEVERE

Ví dụ sau sử dụng **java.util.logging (JUL)** có sẵn trong JDK 17. Một **Handler** minh họa sẽ phát hiện khi có ít nhất **3 bản ghi SEVERE trong 60 giây**. Handler phát **một cảnh báo** khi vượt ngưỡng; các lỗi tiếp theo khi incident đang mở không tạo cảnh báo lặp. Khi đủ 60 giây không còn sự kiện SEVERE trong cửa sổ, việc kiểm tra hồi phục đóng incident.

Ví dụ dùng mốc thời gian cố định để có đầu ra ổn định và dùng **System.out** để **mô phỏng** hành động thông báo. Đây là demo thuật toán, không phải cách triển khai notification production: không có persistence, nhiều instance, hàng đợi bền vững, gửi tới on-call hay cơ chế xử lý log đến muộn.

Tạo tệp **IncidentAlertDemo.java**:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class IncidentAlertDemo {
    private static final Logger LOGGER =
            Logger.getLogger(IncidentAlertDemo.class.getName());

    public static void main(String[] args) {
        LOGGER.setUseParentHandlers(false);
        LOGGER.setLevel(Level.ALL);

        IncidentDetector detector = new IncidentDetector();
        detector.setLevel(Level.ALL);
        LOGGER.addHandler(detector);

        Instant start = Instant.parse("2026-11-09T10:00:00Z");

        failure(start, "Database timeout");
        failure(start.plusSeconds(10), "Database timeout");
        failure(start.plusSeconds(20), "Database timeout");
        failure(start.plusSeconds(30), "Database timeout");

        detector.checkRecovery(start.plusSeconds(95));

        System.out.println("ALERTS_SENT | " + detector.getAlertCount());

        LOGGER.removeHandler(detector);
        detector.close();
    }

    private static void failure(Instant occurredAt, String message) {
        LogRecord record = new LogRecord(Level.SEVERE, message);
        record.setInstant(occurredAt);
        LOGGER.log(record);
    }

    private static final class IncidentDetector extends Handler {
        private static final Duration WINDOW = Duration.ofSeconds(60);
        private static final int THRESHOLD = 3;

        private final Deque<Instant> failureTimes = new ArrayDeque<>();
        private boolean incidentOpen = false;
        private int alertCount = 0;

        @Override
        public void publish(LogRecord record) {
            if (record == null || !isLoggable(record)
                    || record.getLevel().intValue() < Level.SEVERE.intValue()) {
                return;
            }

            Instant now = record.getInstant();
            removeExpired(now);
            failureTimes.addLast(now);

            if (!incidentOpen && failureTimes.size() >= THRESHOLD) {
                incidentOpen = true;
                alertCount++;
                System.out.println(
                        "ALERT | " + now + " | SEVERE >= 3 / 60s");
            }
        }

        void checkRecovery(Instant now) {
            removeExpired(now);
            if (incidentOpen && failureTimes.isEmpty()) {
                incidentOpen = false;
                System.out.println(
                        "RECOVERED | " + now + " | no SEVERE in last 60s");
            }
        }

        int getAlertCount() {
            return alertCount;
        }

        private void removeExpired(Instant now) {
            Instant cutoff = now.minus(WINDOW);
            while (!failureTimes.isEmpty()
                    && failureTimes.peekFirst().isBefore(cutoff)) {
                failureTimes.removeFirst();
            }
        }

        @Override
        public void flush() {
            // Khong co tai nguyen can flush trong vi du nay.
        }

        @Override
        public void close() {
            // Khong co tai nguyen can dong trong vi du nay.
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 IncidentAlertDemo.java
java IncidentAlertDemo
~~~

**Stdout chính xác:**

~~~text
ALERT | 2026-11-09T10:00:20Z | SEVERE >= 3 / 60s
RECOVERED | 2026-11-09T10:01:35Z | no SEVERE in last 60s
ALERTS_SENT | 1
~~~

Giải thích kết quả:

1. Lỗi ở giây 0 và giây 10 chưa đủ ngưỡng; tại giây 20, số lỗi trong cửa sổ 60 giây đạt 3 nên hệ thống tạo **ALERT**.
2. Lỗi thứ tư ở giây 30 vẫn thuộc cùng incident; cờ **incidentOpen** ngăn tạo cảnh báo trùng.
3. Khi kiểm tra ở giây 95, lỗi gần nhất (giây 30) đã cách hơn 60 giây, hàng đợi không còn lỗi trong cửa sổ và demo in **RECOVERED**.
4. Tổng số thông báo mở incident là **1**. Dòng RECOVERED là cập nhật trạng thái, không được đếm là một cảnh báo mở mới.

Đối với **JUL**, Logger và Handler đều có thể lọc theo mức; vì vậy demo đặt cả hai là **Level.ALL** để các bản ghi tới được Handler. Lệnh **setUseParentHandlers(false)** tránh Handler cha in thêm log ra console, giúp đầu ra dự đoán được. **LogRecord.setInstant** có trong Java hiện đại và dùng được với JDK 17.

**Giới hạn cần hiểu:** thuật toán trên giả định các sự kiện tới theo thứ tự thời gian tăng dần, chỉ nhận một luồng log và chỉ kiểm tra hồi phục khi gọi **checkRecovery**. Nếu triển khai thật, quy tắc phải được đánh giá định kỳ, có nguồn dữ liệu bền vững, có xử lý late/duplicate events và giữ trạng thái giữa các lần restart. Trong production, thường để nền tảng quan sát xử lý việc này thay vì cho mỗi JVM tự quyết định và gửi cảnh báo.

## 8. Ghi lỗi trong ứng dụng để hỗ trợ cảnh báo đúng

Ở lớp ứng dụng, code cần ghi đúng **sự kiện có ý nghĩa** và đủ thông tin điều tra. Ví dụ một đoạn minh họa sử dụng biến **logger**, **requestId** và **cause** đã có:

~~~java
logger.log(
        Level.SEVERE,
        "event=PAYMENT_PROVIDER_UNAVAILABLE requestId=" + requestId,
        cause
);
~~~

**Đây chỉ là đoạn mã minh họa**, không phải tệp Java độc lập. Overload **Logger.log(Level, String, Throwable)** giữ tham chiếu tới exception trong **LogRecord** để Formatter có thể ghi stack trace. Không nên thay nguyên nhân bằng riêng chuỗi **cause.getMessage()**, vì sẽ mất vị trí và chuỗi gọi hàm quan trọng.

Nếu log cho mỗi lần retry nhưng request cuối cùng thành công, nên phân biệt **ATTEMPT_FAILED** (lỗi từng lần thử) với **REQUEST_FAILED** (toàn bộ yêu cầu thất bại). Một quy tắc đếm request thất bại phải dựa trên các sự kiện **REQUEST_FAILED** được định nghĩa nhất quán, tránh coi nhiều retry là nhiều khách hàng bị ảnh hưởng.

Trong hệ sinh thái Java, các mức **SEVERE/WARNING/INFO/FINE** thuộc JUL; còn **ERROR/WARN/INFO/DEBUG/TRACE** thường gặp trong SLF4J/Logback. Không gán mức bằng cách so sánh chuỗi tùy tiện giữa framework. Các quy tắc cảnh báo nên ưu tiên **mã sự kiện, trạng thái và tác động**, thay vì chỉ dựa vào tên logging level.

## 9. Từ cảnh báo đến hành động vận hành

Một cảnh báo chỉ có ích nếu người nhận hiểu cần làm gì. Thông điệp cảnh báo nên có:

- **Tên và mức ưu tiên:** “checkout: tỷ lệ 5xx vượt ngưỡng”, mức khẩn cấp theo tác động.
- **Phạm vi:** môi trường production, service bị ảnh hưởng, khu vực hoặc dependency liên quan nếu đã xác minh.
- **Bằng chứng:** số lỗi, tổng yêu cầu, tỷ lệ, cửa sổ thời gian, thời điểm đầu tiên và lần đánh giá gần nhất.
- **Liên kết điều tra:** dashboard, truy vấn log có thời gian và service cụ thể, trace liên quan, mã phiên bản triển khai.
- **Chủ sở hữu và runbook:** nhóm trực, hướng dẫn các bước đầu tiên và cách chuyển cấp khi cần.

Khi tiếp nhận incident, quy trình thường gồm: **xác nhận có ảnh hưởng thực tế**, xem mức độ lan rộng, đối chiếu thay đổi gần nhất, xem log/traces/metrics, áp dụng biện pháp giảm tác động theo runbook, theo dõi hồi phục rồi ghi lại bài học. Hệ thống nên đo **thời gian phát hiện (MTTD)**, thời gian xác nhận và thời gian khôi phục theo định nghĩa thống nhất của tổ chức.

Không để một luồng xử lý request đồng bộ phải chờ hệ thống gửi email, SMS hay webhook cảnh báo. Việc gửi thông báo nên do dịch vụ chuyên dụng đảm nhiệm để lỗi ở kênh cảnh báo không trở thành lỗi mới của nghiệp vụ. Đồng thời, quản lý quyền truy cập vào log và kênh cảnh báo vì chúng có thể chứa bối cảnh vận hành nhạy cảm.

## 10. Sai lầm phổ biến và cách tránh

| Sai lầm | Hậu quả | Cách cải thiện |
| --- | --- | --- |
| Gửi thông báo cho từng bản ghi ERROR | Alert fatigue, người trực bỏ qua tín hiệu thật | Gom nhóm, xác định ngưỡng và giữ trạng thái incident |
| Chỉ nhìn số lượng lỗi tuyệt đối | Dễ nhầm giữa lúc ít và nhiều traffic | Dùng tỷ lệ cùng điều kiện tối thiểu về mẫu số |
| Dùng text message làm khóa cảnh báo | Thay đổi câu chữ làm hỏng rule | Dùng mã sự kiện ổn định và trường có cấu trúc |
| Đếm mọi retry như lỗi nghiệp vụ riêng | Phóng đại quy mô sự cố | Định nghĩa sự kiện terminal outcome hoặc deduplicate theo operation |
| Dùng WARNING/SEVERE làm độ ưu tiên pager một cách máy móc | Báo giả hoặc bỏ sót nguy cơ nghiêm trọng | Xem tác động, tính khẩn cấp và SLO |
| Đóng incident ngay khi không thấy log | Có thể dịch vụ đã ngừng phát log | Kiểm tra heartbeat, lưu lượng, health và độ trễ collector |
| Cảnh báo thiếu ngữ cảnh | Người trực mất thời gian truy tìm | Thêm service, thời gian, truy vấn, dashboard, runbook |
| Dùng Handler trong từng JVM để gửi paging thực tế | Mất trạng thái khi restart, trùng giữa instance | Chuyển luật và quản lý alert sang hệ thống tập trung |
| Ghi secret hoặc dữ liệu nhạy cảm | Rủi ro bảo mật và tuân thủ | Loại bỏ/redact trước khi lưu, kiểm soát quyền và retention |

## 11. Câu hỏi tự kiểm tra

1. **Mọi bản ghi SEVERE có cần đánh thức người trực không?** Không. Mức của log và mức khẩn cấp của alert là hai quyết định khác nhau; phải xét tác động, độ lặp lại và khả năng hành động.
2. **Tại sao không chỉ đếm số lần thất bại?** Vì số lỗi phải đặt trong ngữ cảnh lưu lượng, số lần retry, khoảng thời gian và loại thao tác.
3. **Một ứng dụng không phát log lỗi trong 10 phút có chắc đang khỏe không?** Không. Ứng dụng hoặc pipeline có thể đã ngừng hoạt động; cần health check/heartbeat/metrics.
4. **Khi cùng một điều kiện lỗi vẫn tồn tại ở chu kỳ tiếp theo, có nên mở thêm incident không?** Thường không. Nên cập nhật incident hiện có, gộp và chống lặp thông báo theo chính sách.
5. **Ví dụ Java trên gửi cảnh báo production chưa?** Chưa. Nó chỉ mô phỏng phát hiện và vòng đời cảnh báo bằng stdout để minh họa thuật toán.

**Ghi nhớ:** Logging có thể trở thành nền tảng cho cảnh báo sự cố khi sự kiện được ghi có cấu trúc, được thu thập đáng tin cậy và được đánh giá theo quy tắc phản ánh tác động thực tế. Cảnh báo tốt phải đủ sớm để xử lý, đủ chính xác để người trực tin tưởng và đủ ngữ cảnh để hành động.
