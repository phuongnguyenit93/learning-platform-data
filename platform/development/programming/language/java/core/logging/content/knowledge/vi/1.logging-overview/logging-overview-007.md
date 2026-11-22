# Log trong vòng đời ứng dụng Java

## 1. Mục tiêu: nhìn thấy ứng dụng chuyển trạng thái như thế nào

**Log trong vòng đời ứng dụng** là các bản ghi cho biết ứng dụng đã khởi động đến đâu, khi nào đủ điều kiện nhận việc, đang xử lý gì, gặp lỗi hoặc suy giảm ở bước nào và đã dừng ra sao. Đây là một dòng sự kiện theo thời gian; một thông báo kiểu “đã chạy” không đủ để xác định dịch vụ đã **sẵn sàng phục vụ** hay chưa.

Khi đọc log, người vận hành cần trả lời được: phiên chạy nào phát sinh sự kiện, sự kiện xảy ra ở giai đoạn nào, kết quả là gì, lỗi bắt nguồn từ đâu, và bước nào tiếp theo đã diễn ra. Log hỗ trợ chẩn đoán; trạng thái health/readiness, metrics và trace vẫn có vai trò riêng.

Một vòng đời thường gặp:

```text
PROCESS_START
   → BOOTSTRAP/STARTING
   → INITIALIZING
   → READY
   → RUNNING (nhận và xử lý nhiều công việc)
   → STOPPING (ngừng nhận việc, xử lý nốt việc đang chạy)
   → STOPPED
```

Có các nhánh khác: `STARTING → FAILED`, `RUNNING → DEGRADED → RECOVERED`, `RUNNING → FAILED`. Không phải ứng dụng nào cũng đi qua mọi trạng thái. Nếu tiến trình bị buộc dừng đột ngột, log `STOPPING`/`STOPPED` có thể không tồn tại.

## 2. Đặt log tại các mốc vòng đời

| Giai đoạn | Sự kiện nên ghi | Điều cần đọc được |
| --- | --- | --- |
| Bootstrap | `app.start`, `logging.configured` nếu có | Phiên bản, tên dịch vụ, môi trường, trạng thái bắt đầu; đích và mức log đã thiết lập |
| Khởi tạo | `component.init.start`, `component.init.end`, `component.init.failed` | Thành phần nào đang được tạo, mất bao lâu, có chặn việc khởi động không |
| Sẵn sàng | `app.ready` | Các điều kiện thiết yếu đã đáp ứng, từ thời điểm này dịch vụ có thể nhận việc |
| Vận hành | `request.begin`, `request.end`, `job.start`, `job.finish` | Mã tương quan, kết quả, thời lượng, lỗi nếu có |
| Suy giảm/khôi phục | `dependency.unavailable`, `retry.scheduled`, `dependency.recovered` | Phụ thuộc gặp sự cố gì, tác động, thử lại thế nào, đã phục hồi chưa |
| Dừng có kiểm soát | `app.stopping`, `drain.completed`, `resource.closed`, `app.stopped` | Đã ngừng nhận việc, hoàn thành công việc đang xử lý, giải phóng tài nguyên và đẩy log |
| Dừng do lỗi | `app.failed`, `app.stop_failed` khi còn ghi được | Nguyên nhân cuối cùng, ngoại lệ, giai đoạn gặp lỗi; không khẳng định đã dừng sạch |

### 2.1. Bootstrap và STARTING

Thiết lập logger, mức log, handler/appender, định dạng, đích xuất và chính sách luân chuyển log **càng sớm càng tốt**. Log phát sinh trước khi cấu hình logging hoàn tất có thể đi đến đích mặc định, khác định dạng, hoặc thiếu thông tin ngữ cảnh. Vì vậy, nếu có bootstrap logger, phải xác định rõ đích nhận log sớm và cách bàn giao sang cấu hình chính thức.

Tại `app.start`, ghi các thông tin nhận diện *an toàn*: `service`, `version` hoặc build ID, `environment`, `instanceId` và `event`. Không in toàn bộ biến môi trường, mật khẩu, token, chuỗi kết nối hoặc file cấu hình vì có thể chứa bí mật. Nếu nạp cấu hình thất bại, ghi tên khóa/cấu phần liên quan và nguyên nhân phù hợp, không ghi giá trị nhạy cảm.

Trong giai đoạn `INITIALIZING`, chỉ ghi chi tiết cho những bước giúp tìm nguyên nhân trễ/không khởi động được: tạo pool kết nối, nạp cache bắt buộc, áp dụng cấu hình, kiểm tra phụ thuộc thiết yếu. Với lỗi không thể khắc phục, ghi `component.init.failed` và `app.failed` tại ranh giới chịu trách nhiệm kết thúc tiến trình; tránh lặp cùng một stack trace ở mọi tầng gọi.

### 2.2. READY khác với “hàm main đã chạy”

`READY` là **cam kết ở mức ứng dụng** rằng điều kiện thiết yếu đã thỏa: cấu hình hợp lệ, tài nguyên bắt buộc hoạt động và dịch vụ đã có thể xử lý công việc. Một cổng HTTP đã mở hoặc `main()` đã trả về từ một lệnh khởi tạo chưa đủ để suy ra readiness. Với service có endpoint readiness, chỉ bật trạng thái sẵn sàng khi các điều kiện đó thực sự đạt.

Nếu chưa sẵn sàng, không ghi `app.ready` để “đẹp log”. Nếu khởi động lỗi, ghi trạng thái thất bại và nguyên nhân. Nên có mốc `app.start` cùng `app.ready` để đo thời gian startup; đo thời lượng bằng đồng hồ đơn điệu như `System.nanoTime()`, còn timestamp dùng cho đối chiếu sự kiện giữa hệ thống.

### 2.3. RUNNING: gắn từng công việc vào vòng đời

Khi xử lý một request/job, ghi ít nhất **một kết quả cuối cùng** ở ranh giới chịu trách nhiệm: thành công hay thất bại, mã nghiệp vụ/mã lỗi phù hợp và thời lượng. Ghi `begin` khi việc truy vết thời điểm bắt đầu thực sự hữu ích. Ví dụ:

```text
INFO  event=request.begin requestId=req-42 operation=createOrder
INFO  event=request.end   requestId=req-42 operation=createOrder outcome=success durationMs=18
```

Cả hai dòng cùng `requestId` giúp ghép lại hành trình, nhưng mỗi request phải có ID riêng. Nếu có tracing phân tán, ưu tiên `traceId`/`spanId` để đi qua nhiều service. Với xử lý bất đồng bộ hoặc đổi thread, ngữ cảnh tương quan cần được truyền theo công việc; không nên mặc định `ThreadLocal` tự chuyển sang executor/thread mới. Trong ứng dụng dùng SLF4J và backend hỗ trợ MDC, có thể đặt ID vào MDC theo phạm vi request rồi **xóa/khôi phục ngữ cảnh** ở `finally` để thread tái sử dụng không giữ ID cũ. MDC không phải tính năng mặc định của `java.util.logging` (JUL).

Không ghi mọi bước nhỏ ở mức `INFO` hoặc nguyên văn request/response. Một request thành công thường chỉ cần bản ghi tổng kết; log chi tiết phục vụ điều tra đặt ở `FINE`/DEBUG và phải kiểm soát dung lượng. Tránh ghi dữ liệu cá nhân, khóa truy cập và nội dung nhạy cảm.

### 2.4. DEGRADED, RETRY và RECOVERED

Một phụ thuộc tạm thời không hoạt động chưa chắc khiến cả ứng dụng dừng. Phân biệt:

- **Lỗi từng lần thử:** ghi kèm mã/tên phụ thuộc, retry attempt, chính sách backoff; không tạo hàng nghìn stack trace giống nhau.
- **Chuyển sang suy giảm:** ghi một sự kiện `dependency.unavailable` hoặc `app.degraded` cho lần chuyển trạng thái, kèm tác động.
- **Khôi phục:** ghi `dependency.recovered` hoặc `app.recovered`, kèm thời gian gián đoạn nếu đo được.

Mức log phụ thuộc ảnh hưởng: retry dự kiến có thể ở `FINE` hoặc `WARNING`; mất phụ thuộc bắt buộc khiến không nhận được việc có thể cần `SEVERE`. Log sự kiện chuyển trạng thái dễ theo dõi hơn spam mỗi vòng retry.

### 2.5. STOPPING và STOPPED

Dừng có kiểm soát thường đi theo thứ tự: phát hiện tín hiệu dừng → **ngừng nhận công việc mới** → đợi hoặc hủy công việc đang chạy theo timeout → đóng kết nối và tài nguyên → ghi kết quả dừng → flush các bộ đệm log. Nếu đóng tài nguyên thất bại, ghi `app.stop_failed` cùng nguyên nhân; không ghi `app.stopped` như thể mọi việc đã thành công.

`try/finally` giúp đóng tài nguyên khi một luồng thực thi rời khỏi phạm vi; **JVM shutdown hook** là cơ chế khác dùng khi JVM dừng bình thường hoặc nhận tín hiệu dừng được xử lý. Hook không được bảo đảm chạy khi bị `SIGKILL`, `Runtime.halt()`, mất điện hay JVM crash nghiêm trọng. Hook cần ngắn, có giới hạn chờ, tránh deadlock và không được xem là bảo đảm ghi log cuối cùng. Logger bất đồng bộ cần được drain/flush theo tài liệu backend; tiến trình bị giết đột ngột có thể làm mất các log còn trong bộ đệm.

## 3. Thiết kế nội dung một sự kiện log

Một bản ghi hữu dụng trong sản xuất thường có:

| Trường | Ý nghĩa |
| --- | --- |
| `timestamp`, `level` | Sự kiện xảy ra lúc nào, mức nghiêm trọng |
| `service`, `version`, `instanceId` | Tiến trình/phiên bản nào phát sinh |
| `event`, `state` | Loại sự kiện ổn định và trạng thái vòng đời |
| `requestId` hoặc `traceId` | Ghép các dòng cùng công việc hoặc cùng trace |
| `outcome`, `durationMs` | Kết quả và chi phí thời gian khi phù hợp |
| `errorType`, `errorCode`, ngoại lệ | Chẩn đoán thất bại; stack trace khi cần |

Giữ `event` ổn định để lọc và lập dashboard; để thông tin thay đổi trong các trường riêng. Log dạng JSON thuận tiện cho hệ thống tập trung; log dạng text có cấu trúc vẫn hữu ích khi có cách parse rõ. Timestamp/level có thể do backend tự thêm, không cần nối tay vào mọi message. Đảm bảo đồng hồ hệ thống được đồng bộ để đối chiếu giữa các máy, và dùng duration đo bằng nguồn thời gian đơn điệu để không bị ảnh hưởng khi đồng hồ thay đổi.

Với JUL, các mức thường dùng là `SEVERE` (lỗi nghiêm trọng), `WARNING` (nguy cơ hoặc lỗi có thể phục hồi), `INFO` (mốc vòng đời), `CONFIG`, `FINE`, `FINER`, `FINEST` (thông tin ngày càng chi tiết). **Cả logger và handler đều lọc theo level**: nếu logger cho phép `FINE` nhưng handler chỉ nhận từ `INFO`, bản ghi `FINE` vẫn không xuất hiện. Framework khác có thể dùng ERROR/WARN/INFO/DEBUG/TRACE; đừng coi tên level giữa các thư viện là hoàn toàn đồng nhất.

## 4. Ví dụ Java 17 chạy độc lập bằng java.util.logging

Ví dụ tạo một phiên chạy thành công, phát tín hiệu `STARTING → READY → RUNNING → STOPPING → STOPPED`. Dùng JUL có sẵn trong JDK; formatter rút gọn cho output ổn định và giữ stack trace nếu xuất hiện ngoại lệ. Handler xuất ra **stdout** và flush mỗi sự kiện để dễ quan sát trong ví dụ; sản xuất nên dùng cấu hình handler/backend tập trung thay vì tạo handler tạm thủ công.

Lưu đúng tên tệp `AppLifecycleLoggingDemo.java`:

```java
import java.io.PrintWriter;
import java.io.StringWriter;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public final class AppLifecycleLoggingDemo {
    private static final Logger LOG =
            Logger.getLogger(AppLifecycleLoggingDemo.class.getName());

    public static void main(String[] args) {
        Handler output = new StreamHandler(System.out, new Formatter() {
            @Override
            public String format(LogRecord record) {
                StringBuilder text = new StringBuilder()
                        .append(record.getLevel().getName())
                        .append(" ")
                        .append(formatMessage(record))
                        .append(System.lineSeparator());
                if (record.getThrown() != null) {
                    StringWriter stack = new StringWriter();
                    record.getThrown().printStackTrace(new PrintWriter(stack));
                    text.append(stack);
                }
                return text.toString();
            }
        }) {
            @Override
            public synchronized void publish(LogRecord record) {
                super.publish(record);
                flush();
            }
        };

        output.setLevel(Level.ALL);
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);
        LOG.addHandler(output);

        try {
            LOG.info("event=app.start state=STARTING");
            initialize();
            LOG.info("event=app.ready state=READY");
            processRequest("req-001");
        } catch (RuntimeException e) {
            LOG.log(Level.SEVERE, "event=app.failed state=FAILED", e);
        } finally {
            LOG.info("event=app.stopping state=STOPPING");
            try {
                closeResources();
                LOG.info("event=app.stopped state=STOPPED");
            } catch (RuntimeException e) {
                LOG.log(Level.SEVERE,
                        "event=app.stop_failed state=FAILED", e);
            } finally {
                output.flush();
                LOG.removeHandler(output);
            }
        }
    }

    private static void initialize() {
        // Ví dụ: xác thực cấu hình, mở kết nối bắt buộc.
    }

    private static void processRequest(String requestId) {
        LOG.info("event=request.begin requestId=" + requestId);
        try {
            if (requestId == null || requestId.isBlank()) {
                throw new IllegalArgumentException("requestId is blank");
            }
            LOG.info("event=request.end requestId=" + requestId
                    + " outcome=success");
        } catch (RuntimeException e) {
            LOG.log(Level.SEVERE,
                    "event=request.end requestId=" + requestId
                    + " outcome=failed", e);
            throw e;
        }
    }

    private static void closeResources() {
        // Ví dụ: ngừng nhận request, đợi job, đóng kết nối/pool.
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```bash
javac AppLifecycleLoggingDemo.java
java AppLifecycleLoggingDemo
```

**stdout khi chạy đúng ví dụ:**

```text
INFO event=app.start state=STARTING
INFO event=app.ready state=READY
INFO event=request.begin requestId=req-001
INFO event=request.end requestId=req-001 outcome=success
INFO event=app.stopping state=STOPPING
INFO event=app.stopped state=STOPPED
```

Giải thích: `initialize()` kết thúc trước khi phát `app.ready`; yêu cầu `req-001` có cả `begin` và `end`; `finally` thực hiện nhánh dừng kể cả khi xử lý bên trong ném `RuntimeException`. `setUseParentHandlers(false)` tránh bản ghi bị in thêm bởi console handler mặc định; `setLevel` trên cả logger và handler cho phép sự kiện được ghi. Formatter đưa stack trace vào log khi nhận `LogRecord.getThrown()` khác `null`. Trong mã thực, `initialize()` và `closeResources()` phải có triển khai tương ứng và chính sách timeout.

Ví dụ tập trung vào thứ tự sự kiện. Nó không có vòng nhận HTTP, không lắp shutdown hook, và không đo duration. Với dịch vụ chạy lâu, mốc `STOPPING` cần gắn với tín hiệu dừng thực tế; không suy ra `finally` của `main` đại diện cho mọi kiểu tắt JVM. Nếu startup thất bại nghiêm trọng, ứng dụng thực cần quyết định exit code khác 0/đánh dấu health thất bại ở ranh giới khởi động; **chỉ ghi `SEVERE` rồi thoát với mã thành công có thể làm hệ thống giám sát hiểu nhầm**.

## 5. Đọc chuỗi log để tìm lỗi

Giả sử hệ thống không nhận request sau khi triển khai:

```text
INFO    event=app.start state=STARTING version=2.4.0
INFO    event=component.init.start component=database
SEVERE  event=component.init.failed component=database errorType=ConnectException
SEVERE  event=app.failed state=FAILED
INFO    event=app.stopping state=STOPPING
INFO    event=app.stopped state=STOPPED
```

Chuỗi này cho thấy tiến trình **chưa từng đạt READY**; lỗi trong quá trình khởi tạo cơ sở dữ liệu, không phải lỗi xử lý một request. `STOPPED` chỉ cho biết quá trình dọn dẹp đã kết thúc, không có nghĩa phiên chạy thành công. Khi hệ thống đang phục vụ rồi phụ thuộc chập chờn, tìm sự kiện chuyển `DEGRADED`/`RECOVERED` và đối chiếu requestId/traceId của các request thất bại trong khoảng đó.

Cần lưu ý **một log bị thiếu không tự chứng minh sự kiện không xảy ra**: log có thể bị lọc theo level, chưa flush, bị mất trên đường chuyển hoặc không được tạo do tiến trình dừng đột ngột. Kết hợp log với exit code, health check, metrics, traces và dữ liệu deployment khi kết luận.

## 6. Các lỗi triển khai thường gặp

1. **Ghi READY quá sớm:** chương trình đã bind cổng nhưng chưa kiểm tra phụ thuộc bắt buộc. Chỉ ghi READY và bật readiness khi thực sự có thể nhận việc.
2. **Không có điểm kết thúc cho công việc:** chỉ có `request.begin` khiến khó biết request treo hay kết thúc. Ghi `request.end`/`request.failed` tại ranh giới chịu trách nhiệm, kể cả trong luồng lỗi.
3. **Lặp cùng một ngoại lệ ở nhiều tầng:** một lỗi bị log `SEVERE` ở repository, service và controller làm sai cảm nhận số lượng sự cố. Tầng có quyền quyết định xử lý/thoát nên log đầy đủ; tầng dưới có thể thêm ngữ cảnh rồi ném tiếp.
4. **Mất correlation khi chạy bất đồng bộ:** job đổi thread nhưng không truyền traceId/requestId. Truyền ngữ cảnh rõ ràng và dọn context sau khi xử lý.
5. **Chỉ dựa vào STOPPED/hook:** dừng cưỡng bức có thể làm mất log cuối. Cần theo dõi trạng thái tiến trình, exit code và health độc lập.
6. **Để secret trong log khởi động/lỗi:** cấu hình, URI, exception message có thể chứa token hoặc mật khẩu. Mask/loại các trường đó trước khi ghi và kiểm soát quyền truy cập/retention.
7. **Ghi quá nhiều ở INFO hoặc không flush:** log ngập bởi retry/request chi tiết hoặc mất do buffer khi sự cố. Chọn level, sampling/rate limit và cơ chế flush thích hợp.
8. **Nhầm event với metric:** một dòng `durationMs=...` giúp điều tra một request; histogram/alert cần hệ thống metrics phù hợp.

## 7. Checklist khi thiết kế log theo vòng đời

- Xác định các trạng thái có thật của ứng dụng và những chuyển trạng thái cần ghi; đặt `app.ready` sau điều kiện sẵn sàng.
- Ghi tên dịch vụ/phiên bản, event ổn định, trạng thái và ID tương quan; đo thời lượng ở nơi sở hữu công việc.
- Bao phủ cả thành công, khởi tạo thất bại, suy giảm/phục hồi và dừng; ghi nguyên nhân lỗi tại đúng ranh giới, giữ stack trace khi cần.
- Khi dừng, ngừng nhận việc, xử lý phần đang chạy, đóng tài nguyên, báo kết quả dọn dẹp và flush log trong khả năng cho phép.
- Kiểm tra phân mức logger/handler, đầu ra thực tế, bí mật bị che, quy tắc retention và liên kết log–trace–metric.
- Thử ít nhất bốn kịch bản: startup thành công, startup thất bại, request thất bại, shutdown có kiểm soát; mô phỏng crash để hiểu log có thể thiếu.

Mấu chốt là **log phải phản ánh chính xác việc chuyển trạng thái và kết quả xử lý**, giúp tái dựng vòng đời của từng phiên ứng dụng mà không cần suy đoán từ một dòng “started” hoặc “stopped”.
