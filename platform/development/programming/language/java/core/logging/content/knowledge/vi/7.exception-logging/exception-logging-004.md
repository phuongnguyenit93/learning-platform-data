# Lỗi có thể xử lý trong Exception Logging (Java)

## 1. Hiểu đúng lỗi có thể xử lý

Trong Java, **lỗi có thể xử lý** là tình huống bất thường mà chương trình có cách phục hồi đã được thiết kế: thử lại an toàn, dùng phương án dự phòng, trả lỗi nghiệp vụ có kiểm soát hoặc tiếp tục với trạng thái vẫn đúng. Ví dụ, một lần gọi dịch vụ bên ngoài timeout nhưng thử lại thành công, cache lỗi nhưng dữ liệu nguồn vẫn truy cập được, hoặc một cấu hình tùy chọn thiếu và có giá trị mặc định an toàn.

**Bắt được exception chưa đồng nghĩa với xử lý thành công.** Một khối catch chỉ in thông báo rồi bỏ qua có thể làm hệ thống tiếp tục với dữ liệu sai. Exception handling quyết định cách chương trình phản ứng; exception logging tạo bằng chứng để người phát triển và vận hành hiểu điều gì đã xảy ra.

Khả năng phục hồi **phụ thuộc ngữ cảnh**. IOException khi đọc cache có thể được xử lý bằng cách đọc từ database, nhưng IOException khi ghi dữ liệu tài chính bắt buộc có thể khiến giao dịch phải thất bại. Checked exception và unchecked exception chỉ là cách Java phân loại nghĩa vụ khai báo/bắt lỗi; chúng không mặc nhiên tương ứng với mức độ nghiêm trọng của sự cố.

Trong một yêu cầu, nên phân biệt:

- **Attempt failed:** Một lần thử riêng lẻ thất bại; vẫn còn cơ chế phục hồi.
- **Recovered:** Yêu cầu hoặc thao tác cuối cùng thành công sau retry/fallback.
- **Degraded:** Hệ thống trả kết quả đúng theo hợp đồng nhưng phải dùng phương án dự phòng hoặc giảm một phần chức năng.
- **Operation failed:** Không còn cách xử lý an toàn; thao tác cuối cùng thất bại và phải trả kết quả lỗi phù hợp.

Một yêu cầu có thể có ba lần thử thất bại nhưng **không có lỗi cuối cùng** nếu lần thứ tư thành công. Log và metric cần phản ánh rõ khác biệt này.

## 2. Chọn log level theo tác động của lỗi

Tùy thư viện Java, tên mức log khác nhau. Java Util Logging (**java.util.logging**, JUL) dùng **SEVERE, WARNING, INFO, CONFIG, FINE, FINER, FINEST**. SLF4J và các backend phổ biến thường dùng **ERROR, WARN, INFO, DEBUG, TRACE**.

| Trạng thái | JUL gợi ý | SLF4J gợi ý | Lý do |
| --- | --- | --- | --- |
| Một retry thất bại nhưng được phục hồi theo đúng thiết kế | FINE hoặc WARNING tùy mức bất thường | DEBUG hoặc WARN | Không làm người trực hiểu nhầm mỗi lần thử là thất bại toàn bộ |
| Fallback được kích hoạt và dịch vụ suy giảm | WARNING | WARN | Hệ thống hoạt động khác đường chính, đáng theo dõi |
| Hoàn thành sau khi phục hồi | INFO nếu sự kiện có giá trị vận hành | INFO | Cho biết kết quả cuối cùng thành công |
| Dữ liệu người dùng không hợp lệ theo hợp đồng API | Thường không cần SEVERE; INFO/FINE hoặc không ghi | INFO/DEBUG hoặc không ghi | Lỗi đầu vào hợp lệ về mặt vận hành không nhất thiết là lỗi hệ thống |
| Yêu cầu quan trọng thất bại sau mọi cách phục hồi | SEVERE | ERROR | Cần ghi rõ kết quả thất bại và nguyên nhân |
| Bất biến hệ thống bị vi phạm hoặc bug chưa khắc phục | SEVERE tại điểm xử lý cuối | ERROR tại điểm xử lý cuối | Thường cần giữ stack trace và điều tra |

Đây là hướng dẫn chọn mức, **không phải ánh xạ chính xác giữa JUL và SLF4J ở mọi bridge**. Chọn mức dựa trên tác động, tần suất, khả năng hành động và quy ước dự án.

Ví dụ, retry mạng xảy ra 100 lần mỗi giây và hầu hết thành công có thể chỉ cần FINE/DEBUG cùng metric **retry_count**. Ghi WARNING kèm stack trace cho mọi attempt có thể tạo quá nhiều log. Ngược lại, hệ thống kích hoạt fallback hiếm gặp ở một chức năng quan trọng có thể đáng ghi WARNING.

## 3. Các chiến lược xử lý lỗi phổ biến

### 3.1. Retry có giới hạn

Retry hữu ích khi lỗi có khả năng tạm thời và thao tác **an toàn để thực hiện lại**. Có thể áp dụng với một số lỗi kết nối, timeout hoặc phản hồi 503, tùy hợp đồng API và loại thao tác.

Một quy trình phù hợp:

1. Xác định nhóm exception được phép retry, không bắt rộng mọi Exception.
2. Đặt giới hạn số lượt và tổng thời gian; tránh vòng lặp vô hạn.
3. Nếu cần, áp dụng backoff và jitter để giảm nguy cơ nhiều client retry cùng lúc.
4. Tôn trọng deadline, cancellation và tín hiệu ngắt luồng.
5. Nếu thành công, trả kết quả và phát sự kiện recovered khi cần.
6. Nếu hết lượt, ghi thất bại cuối cùng ở ranh giới chịu trách nhiệm, giữ nguyên cause.

**Timeout không chứng minh phía server chưa thực hiện thao tác.** Với thanh toán, tạo đơn, gửi email hoặc thao tác ghi, retry có thể gây tác dụng phụ lặp nếu thiếu idempotency key hoặc cơ chế deduplicate. Không retry một thao tác không idempotent chỉ vì có IOException.

### 3.2. Fallback có kiểm soát

Ví dụ cache không truy cập được nhưng database vẫn hoạt động:

~~~text
Read cache
  -> IOException
  -> chuyển sang đọc từ database
  -> database trả dữ liệu đúng
  -> kết quả thành công, ghi nhận fallback nếu đáng quan tâm
~~~

Fallback chỉ là phục hồi nếu đáp ứng hợp đồng nghiệp vụ. Không tự dùng giá trị mặc định giả cho dữ liệu thanh toán, quyền truy cập hay khóa mã hóa bắt buộc.

Nếu fallback xuất hiện liên tục, đó có thể là suy giảm hiệu năng cần xử lý. Nên có metric về số lần fallback và mức tác động; tránh spam cùng một cảnh báo cho từng request.

### 3.3. Chuyển lỗi đầu vào thành phản hồi có kiểm soát

Người dùng gửi ngày sai định dạng có thể nhận HTTP 400 hoặc thông báo kiểm tra dữ liệu theo hợp đồng API. Đây là lỗi đầu vào được dự kiến, không nhất thiết phải tạo một log ERROR kèm stack trace. Hạn chế ghi toàn bộ request vì có thể chứa dữ liệu cá nhân.

### 3.4. Truyền tiếp khi không thể phục hồi

Tầng Repository có thể không biết yêu cầu nghiệp vụ có cho phép retry hay không. Khi đó nên truyền exception, có thể bọc với ngữ cảnh và nguyên nhân, để tầng Service hoặc API boundary quyết định. Ghi lỗi SEVERE ở mọi tầng rồi ném tiếp sẽ làm một sự cố xuất hiện nhiều lần trong log.

## 4. Ví dụ Java 17 độc lập: lỗi tạm thời và lỗi sau khi hết retry

Ví dụ sử dụng **java.util.logging (JUL)** có sẵn trong JDK. Một dependency giả lập gặp lỗi I/O trước khi trả kết quả; không có lời gọi mạng hoặc tác dụng phụ thật.

- **req-A** thất bại một lần, sau đó thành công ở lần thử thứ hai.
- **req-B** thất bại cho đến khi hết hai lần thử. Phương thức xử lý ghi lỗi cuối, ném lại IOException; tầng gọi chuyển thành một kết quả thất bại có kiểm soát mà không ghi trùng.

Tạo tệp **RecoverableExceptionLoggingDemo.java**:

~~~java
import java.io.IOException;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class RecoverableExceptionLoggingDemo {
    private static final Logger LOGGER =
            Logger.getLogger(RecoverableExceptionLoggingDemo.class.getName());

    public static void main(String[] args) throws Exception {
        Handler output = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (!isLoggable(record)) {
                    return;
                }

                String cause = record.getThrown() == null
                        ? ""
                        : " | cause="
                            + record.getThrown().getClass().getSimpleName();

                System.out.println(
                        record.getLevel().getName()
                        + " | " + record.getMessage()
                        + cause);
            }

            @Override
            public void flush() {
                // Khong co bo dem can flush.
            }

            @Override
            public void close() {
                // Khong so huu tai nguyen can dong.
            }
        };

        output.setLevel(Level.ALL);
        LOGGER.setUseParentHandlers(false);
        LOGGER.setLevel(Level.INFO);
        LOGGER.addHandler(output);

        try {
            System.out.println("SCENARIO | temporary failure");
            process("req-A", new ExampleGateway(1), 3);

            System.out.println("SCENARIO | retries exhausted");
            try {
                process("req-B", new ExampleGateway(9), 2);
            } catch (IOException e) {
                // Exception da duoc log tai diem xac dinh ket qua cuoi.
                System.out.println("RESULT | req-B | failed");
            }
        } finally {
            LOGGER.removeHandler(output);
            output.close();
        }
    }

    private static void process(
            String requestId,
            ExampleGateway gateway,
            int maxAttempts) throws IOException {

        if (maxAttempts < 1) {
            throw new IllegalArgumentException("maxAttempts must be >= 1");
        }

        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                String result = gateway.send();

                if (attempt > 1) {
                    LOGGER.info(
                            "RECOVERED requestId=" + requestId
                            + " attempts=" + attempt);
                }

                System.out.println(
                        "RESULT | " + requestId + " | " + result);
                return;
            } catch (IOException e) {
                if (attempt < maxAttempts) {
                    LOGGER.log(
                            Level.WARNING,
                            "RETRY_SCHEDULED requestId=" + requestId
                            + " attempt=" + attempt,
                            e);
                } else {
                    LOGGER.log(
                            Level.SEVERE,
                            "OPERATION_FAILED requestId=" + requestId
                            + " attempts=" + attempt,
                            e);
                    throw e;
                }
            }
        }
    }

    private static final class ExampleGateway {
        private int failuresRemaining;

        private ExampleGateway(int failuresBeforeSuccess) {
            failuresRemaining = failuresBeforeSuccess;
        }

        String send() throws IOException {
            if (failuresRemaining > 0) {
                failuresRemaining--;
                throw new IOException("temporary unavailability");
            }
            return "accepted";
        }
    }
}
~~~

Biên dịch và chạy với **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 RecoverableExceptionLoggingDemo.java
java RecoverableExceptionLoggingDemo
~~~

**Stdout chính xác theo logic chương trình:**

~~~text
SCENARIO | temporary failure
WARNING | RETRY_SCHEDULED requestId=req-A attempt=1 | cause=IOException
INFO | RECOVERED requestId=req-A attempts=2
RESULT | req-A | accepted
SCENARIO | retries exhausted
WARNING | RETRY_SCHEDULED requestId=req-B attempt=1 | cause=IOException
SEVERE | OPERATION_FAILED requestId=req-B attempts=2 | cause=IOException
RESULT | req-B | failed
~~~

Giải thích:

1. Lần đầu của **req-A** ném IOException. Vì còn lượt thử, phương thức ghi WARNING với mã **RETRY_SCHEDULED** và tham chiếu tới Throwable.
2. Lần thứ hai của req-A trả về **accepted**, nên ghi INFO **RECOVERED**. Không ghi SEVERE bởi yêu cầu cuối cùng thành công.
3. Với **req-B**, lần thứ nhất chỉ là attempt failure; lần thứ hai là lỗi cuối cùng, nên ghi **SEVERE OPERATION_FAILED** và **throw e**.
4. Tầng gọi bắt exception, biểu diễn kết quả thất bại, **không ghi lại cùng exception**. Một thao tác cuối cùng thất bại không bị biến thành nhiều lỗi nghiêm trọng do log trùng.
5. **LOGGER.log(Level, String, Throwable)** giữ Throwable trong bản ghi. Handler của demo chỉ in kiểu IOException để đầu ra đơn giản; Formatter production có thể in stack trace và cause chain.
6. Handler được đặt **Level.ALL**, Logger ở **Level.INFO**, còn **setUseParentHandlers(false)** ngăn dòng log mặc định từ Handler của cha. Handler demo chủ động in ra **stdout**; ConsoleHandler chuẩn của JUL thường in ra **stderr**.

Đây là ví dụ sư phạm. Để chạy trong production cần bổ sung timeout, retry budget, backoff/jitter, idempotency, trạng thái giao dịch, cancellation và cơ chế quan sát phù hợp. Đặc biệt, **không sao chép vòng retry này cho API thanh toán thật** mà không có đảm bảo chống xử lý trùng.

## 5. Ghi exception kèm nguyên nhân, tránh mất stack trace

### 5.1. Chỉ ghi getMessage() chưa đủ khi cần điều tra

Đoạn minh họa trong một class có LOGGER và phương thức readRemote():

~~~java
try {
    readRemote();
} catch (IOException e) {
    LOGGER.warning("Remote failed: " + e.getMessage());
}
~~~

Thông điệp có thể hiển thị lỗi, nhưng LogRecord không tự chứa Throwable nếu chỉ truyền chuỗi như vậy. Kết quả là thiếu stack trace, cause chain và dữ liệu kỹ thuật cho Formatter. Hơn nữa, một số exception message do dependency tạo có thể vô tình chứa URL, dữ liệu đầu vào hoặc thông tin nhạy cảm.

Khi cần nguyên nhân, dùng overload JUL nhận **Throwable**:

~~~java
try {
    readRemote();
} catch (IOException e) {
    LOGGER.log(
            Level.WARNING,
            "REMOTE_READ_RETRYABLE operation=fetchCatalog",
            e);
}
~~~

**Hai đoạn trên là ví dụ đặt trong phương thức đã có các thành phần liên quan; không phải tệp độc lập.** Chú ý: trong catch cần thực sự retry, fallback hoặc truyền tiếp nếu chưa xử lý được. Ghi log không thay thế hành động xử lý lỗi.

### 5.2. Khi bọc exception hãy giữ cause

~~~java
try {
    persistOrder(orderId);
} catch (IOException e) {
    throw new IllegalStateException(
            "Order persistence failed for request " + requestId,
            e);
}
~~~

Overload constructor với **e** giữ nguyên nhân gốc. Nếu tầng dưới chỉ thêm ngữ cảnh rồi ném tiếp, thường không cần log lỗi ngay tại đây khi tầng trên đã chịu trách nhiệm ghi lỗi cuối. Ghi cùng stack trace ở Repository, Service và Controller thường tạo nhiễu hơn là giúp điều tra.

### 5.3. Đếm attempt khác đếm operation

Một request có thể có ba dòng **ATTEMPT_FAILED** nhưng cuối cùng thành công. Nếu dashboard đếm mỗi dòng này thành một request thất bại, tỷ lệ lỗi sẽ bị thổi phồng. Nên có **event_code**, **operation**, **attempt**, **request_id** và **outcome** ổn định; metric về kết quả cuối cùng cần được tính ở ranh giới kết thúc thao tác.

## 6. Cấu hình mức log cho lỗi recoverable

JUL có ngưỡng ở **Logger** và **Handler**. Ví dụ:

~~~java
LOGGER.setLevel(Level.FINE);
handler.setLevel(Level.INFO);
~~~

Lời gọi LOGGER.fine(...) vẫn có thể không xuất ra đích vì Handler chặn. Nếu Logger đặt ở INFO, FINE có thể bị chặn trước khi tạo bản ghi. Trong ứng dụng có nhiều Handler hoặc logger kế thừa từ cha, cần kiểm tra toàn bộ tuyến xử lý.

Thông thường, production dùng **INFO** làm điểm khởi đầu và bật **FINE/DEBUG** theo class khi điều tra. Retry bình thường có thể ghi mức FINE; event phục hồi đáng chú ý dùng INFO; fallback liên tục hoặc suy giảm dùng WARNING; lỗi cuối cùng của chức năng thiết yếu dùng SEVERE. Nhưng **không có mức bắt buộc cho mọi dự án**.

Với JUL, tránh tạo chuỗi chẩn đoán đắt tiền trước lời gọi bị chặn:

~~~java
LOGGER.log(
        Level.FINE,
        () -> "Diagnostics: " + buildExpensiveDetails()
);
~~~

Đây là đoạn minh họa có **buildExpensiveDetails()** đã tồn tại. Dạng Supplier hoãn tính toán message khi Logger không chấp nhận FINE; Handler vẫn có thể lọc sau đó. Với SLF4J, API có cú pháp placeholder khác, thường là **{}**; không dùng placeholder của SLF4J trong JUL rồi kỳ vọng tự định dạng tương tự.

## 7. Cấu hình tùy chọn và fallback có giá trị mặc định

Có thể dùng default khi một cấu hình **không bắt buộc** bị thiếu hoặc sai định dạng, với điều kiện giá trị mặc định là an toàn và được thiết kế trước. Đoạn minh họa sau nằm trong phương thức đã có **Properties properties**, **long timeoutMillis** và **LOGGER**:

~~~java
String raw = properties.getProperty("client.timeout.ms");

if (raw == null) {
    LOGGER.info("CONFIG_DEFAULT_USED key=client.timeout.ms");
    timeoutMillis = 2000L;
} else {
    try {
        long parsed = Long.parseLong(raw);
        if (parsed <= 0) {
            LOGGER.warning(
                    "INVALID_OPTIONAL_CONFIG key=client.timeout.ms");
            timeoutMillis = 2000L;
        } else {
            timeoutMillis = parsed;
        }
    } catch (NumberFormatException e) {
        LOGGER.log(
                Level.WARNING,
                "INVALID_OPTIONAL_CONFIG key=client.timeout.ms",
                e);
        timeoutMillis = 2000L;
    }
}
~~~

Con số 2000 ms chỉ là ví dụ. Dự án thật còn phải kiểm tra giới hạn tối đa, hợp đồng timeout và yêu cầu bảo mật. **Cấu hình bắt buộc** như khóa mã hóa hoặc quyền truy cập không được âm thầm thay bằng giá trị giả chỉ để ứng dụng tiếp tục khởi động.

## 8. Những exception không nên xử lý theo kiểu retry thông thường

**InterruptedException** thể hiện tín hiệu ngắt/hủy khi luồng đang chờ. Nếu phương thức không truyền tiếp được exception này, thông thường cần khôi phục cờ ngắt và kết thúc công việc phù hợp:

~~~java
try {
    Thread.sleep(500);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    LOGGER.log(Level.FINE, "Retry wait interrupted", e);
    return;
}
~~~

Đây là **đoạn minh họa trong phương thức void**. Nếu phương thức được phép khai báo throws InterruptedException, truyền tiếp cũng có thể phù hợp. Không nuốt tín hiệu hủy rồi lặp retry vô hạn.

**NullPointerException** do bug nội bộ hoặc **IllegalStateException** cho trạng thái không hợp lệ thường đòi hỏi sửa logic, không chỉ catch rồi tiếp tục. Những **Error** nghiêm trọng như OutOfMemoryError không nên bị catch rộng như lỗi nghiệp vụ bình thường.

**Không catch Exception chỉ để “đảm bảo không lỗi”.** Catch nên có mục đích cụ thể: khôi phục, chuyển lỗi thành kết quả được định nghĩa, đóng/rollback tài nguyên hoặc thêm ngữ cảnh trước khi chuyển lên tầng có trách nhiệm. Dùng try-with-resources với tài nguyên AutoCloseable khi phù hợp để tránh rò rỉ dù gặp exception.

## 9. Vì sao log trùng có hại?

Giả sử một lần ghi database thất bại trong Repository. Nếu Repository log ERROR rồi ném tiếp, Service log ERROR rồi ném tiếp, Controller lại log ERROR, người trực có thể thấy ba lỗi tưởng như ba sự cố.

Một lựa chọn rõ ràng hơn:

- **Repository:** truyền exception hoặc bọc lại cùng cause và ngữ cảnh kỹ thuật, không ghi lỗi cuối nếu nó chưa xử lý.
- **Service:** thực hiện retry/fallback hợp lệ; ghi một sự kiện chuyển trạng thái khi đáng quan tâm.
- **API boundary hoặc tầng kết thúc nghiệp vụ:** biết thao tác cuối cùng thành công hay thất bại và ghi một bản ghi lỗi cuối phù hợp.

Không có quy tắc cứng rằng chỉ một log có thể tồn tại trong mọi trường hợp; một log chẩn đoán riêng ở tầng thấp và một log tổng hợp ở boundary có thể hợp lý nếu chúng mang **thông tin khác nhau**. Điều cần tránh là lặp cùng exception và stack trace ở mọi tầng mà không bổ sung ngữ cảnh.

## 10. Log có cấu trúc để phân biệt lỗi tạm với lỗi cuối

Đối với recoverable error, các trường sau có giá trị:

| Trường | Mục đích |
| --- | --- |
| **timestamp** | Thời điểm sự kiện, có múi giờ rõ ràng |
| **level** | Mức log, chẳng hạn WARNING hoặc SEVERE |
| **service/logger_name** | Thành phần phát sinh |
| **event_code** | Mã ổn định như RETRY_SCHEDULED hoặc OPERATION_FAILED |
| **request_id/trace_id** | Liên kết các attempt thuộc cùng yêu cầu |
| **operation** | Thao tác cụ thể như fetchCatalog |
| **attempt/max_attempts** | Lần thử và ngân sách retry |
| **exception_type/cause** | Loại lỗi và chuỗi nguyên nhân |
| **outcome** | retrying, recovered, degraded hoặc failed |

Ví dụ JSON mang tính khái niệm:

~~~json
{
  "timestamp": "2026-11-09T10:00:00Z",
  "level": "WARN",
  "service": "checkout",
  "logger_name": "com.example.gateway.Client",
  "event_code": "RETRY_SCHEDULED",
  "request_id": "req-A",
  "operation": "authorize",
  "attempt": 1,
  "max_attempts": 3,
  "exception_type": "IOException",
  "outcome": "retrying"
}
~~~

**Đây không phải JSON tự động sinh bởi JUL.** Cần Formatter/encoder và cơ chế truyền correlation phù hợp. Event code giúp truy vấn ổn định hơn so với dò câu chữ message. Không đưa access token, password, session cookie, khóa bí mật, payload thanh toán hoặc dữ liệu cá nhân nhạy cảm vào log ở bất kỳ mức nào.

## 11. Metrics và cảnh báo cho lỗi tự phục hồi

Log trả lời **đã xảy ra điều gì và vì sao**. Metrics có thể trả lời **bao nhiêu lần và mức ảnh hưởng ra sao**. Với lỗi recoverable nên quan sát:

- **retry_count / retry_rate:** Tần suất phải thử lại.
- **fallback_count / fallback_rate:** Tần suất dùng đường dự phòng.
- **operation_failure_rate:** Tỷ lệ thao tác cuối cùng thất bại.
- **latency p95/p99:** Retry thành công có thể vẫn làm tăng độ trễ.
- **circuit-breaker state / dependency health:** Phát hiện thành phần phụ đang suy giảm.

Ví dụ một request có bốn attempts, trong đó ba lần đầu thất bại rồi lần cuối thành công: metrics nên phản ánh **ba lỗi attempt** và **một operation thành công**. Đừng để hệ thống cảnh báo coi mọi log WARNING/ERROR là sự cố cần gọi người trực ngay.

Nếu pipeline log bị mất hoặc giảm mẫu, không nên suy ra số lượng request tuyệt đối từ log mà không kiểm tra độ tin cậy. Metric chuyên dụng và tracing bổ sung cho log trong việc quan sát hành vi hệ thống.

## 12. Chi phí và an toàn của exception logging

Nếu dịch vụ xử lý **1.000 yêu cầu/giây**, **10%** cần retry và mỗi attempt failure ghi stack trace khoảng **2 KB**, lượng log chỉ riêng phần này đã là:

~~~text
1.000 request/s × 10% = 100 retry/s
100 retry/s × 2.000 byte = 200.000 byte/s
200.000 byte/s × 86.400 s = 17,28 GB/ngày
~~~

Số này chưa tính indexing, metadata hoặc sao chép. Khi retry là tình huống thường xuyên và được phục hồi, ưu tiên FINE/DEBUG, metric tổng hợp hoặc giới hạn tần suất phù hợp; vẫn phải giữ bằng chứng lỗi cuối quan trọng.

Dữ liệu lỗi từ thư viện ngoài không mặc định an toàn. Exception message có thể chứa URL, headers hoặc thông tin người dùng. Thiết kế quy tắc redaction, quyền đọc, retention và auditing của hệ thống log, đồng thời tránh ghi nguyên request/response khi chỉ cần ID kỹ thuật.

## 13. Những lỗi thường gặp và cách sửa

| Lỗi trong code hoặc vận hành | Rủi ro | Cách xử lý |
| --- | --- | --- |
| Catch Exception rồi bỏ qua | Che lỗi, để trạng thái sai | Chỉ bắt loại cần xử lý; fallback hoặc truyền tiếp đúng cách |
| Ghi mọi retry là SEVERE | Báo động giả, phóng đại tỷ lệ lỗi | Tách ATTEMPT_FAILED khỏi OPERATION_FAILED |
| Chỉ ghi e.getMessage() | Mất Throwable và stack trace | Dùng overload có Throwable khi cần |
| Log ở mọi tầng rồi rethrow | Một lỗi có nhiều bản ghi trùng | Phân rõ boundary ghi lỗi cuối |
| Retry không giới hạn | Tăng tải, chậm hoặc lặp vô hạn | Giới hạn lượt, tổng thời gian và backoff |
| Retry thao tác có side effect không idempotent | Tạo giao dịch/đơn trùng | Dùng idempotency key và kiểm tra hợp đồng |
| Bỏ qua InterruptedException | Không dừng tác vụ khi bị hủy | Truyền tiếp hoặc khôi phục interrupt flag |
| Dùng default cho cấu hình bắt buộc | Ứng dụng chạy sai hoặc không an toàn | Fail có kiểm soát, không fallback giả |
| Ghi payload/secret ở DEBUG | Rò rỉ dữ liệu | Chỉ ghi trường cần thiết, redaction |
| Chỉ dựa vào số dòng lỗi để paging | Sai tác động, nhiều cảnh báo giả | Dùng metric kết quả cuối và SLO |
| Ghi phục hồi trước khi thực sự hoàn tất | Nhật ký sai sự thật | Chỉ ghi recovered sau bước được xác nhận thành công |

## 14. Checklist trước khi hoàn thành một catch

1. Xác định **exception này có thực sự recoverable trong ngữ cảnh hiện tại**.
2. Chọn retry, fallback, trả lỗi nghiệp vụ hoặc ném tiếp có nguyên nhân.
3. Kiểm tra **idempotency**, giới hạn retry, deadline và tính đúng đắn trạng thái.
4. Chọn log level theo **kết quả cuối và tác động**, không theo tên exception đơn thuần.
5. Giữ Throwable/cause khi cần chẩn đoán và tránh chỉ giữ message.
6. Ghi event code, request ID, operation, attempt và outcome ở nơi phù hợp.
7. Không log trùng cùng sự cố ở nhiều tầng thiếu giá trị bổ sung.
8. Không ghi token, mật khẩu, dữ liệu nhạy cảm; kiểm soát quyền và retention.
9. Có metric về retry/fallback/failure, cũng như điều kiện cảnh báo khi tự phục hồi không còn đủ.
10. Bảo đảm hủy luồng, rollback và đóng tài nguyên theo đúng hợp đồng.

## 15. Câu hỏi tự kiểm tra

**1.** Một lần IOException xuất hiện nhưng retry thành công. Có bắt buộc ghi SEVERE không?

Không. Kết quả cuối cùng thành công; có thể ghi FINE/WARNING cho attempt và INFO cho recovered, tùy tần suất và mức quan trọng.

**2.** Logger.warning(e.getMessage()) có bảo toàn stack trace trong LogRecord không?

Không. Cần truyền đối tượng Throwable bằng overload phù hợp khi cần chẩn đoán.

**3.** Vì sao timeout khi thanh toán không có nghĩa chắc chắn nên retry?

Vì server có thể đã thực hiện giao dịch rồi mất phản hồi; retry thiếu idempotency có thể tạo thanh toán trùng.

**4.** Một yêu cầu có ba attempt thất bại rồi thành công nên được tính là bao nhiêu thao tác cuối cùng thất bại?

**Không có thao tác cuối thất bại**; đó là ba attempt failed và một operation thành công.

**5.** Vì sao không nên catch InterruptedException rồi lặp tiếp?

Vì đó là tín hiệu hủy. Cần truyền tiếp hoặc khôi phục cờ interrupt và chấm dứt xử lý phù hợp.

**6.** Một tầng thấp đã log exception và ném tiếp; tầng cao log lại cùng exception có luôn cần thiết không?

Không. Nên phân công ranh giới chịu trách nhiệm và tránh stack trace trùng, trừ khi có thông tin khác biệt thực sự hữu ích.

**Ghi nhớ:** Lỗi có thể xử lý là lỗi có **phương án phục hồi đúng và có giới hạn**. Hãy ghi nhận sự kiện theo tác động thật, giữ cause khi điều tra, phân biệt lỗi từng attempt với thất bại cuối cùng và quan sát cả trường hợp phục hồi lẫn suy giảm để vận hành Java an toàn.
