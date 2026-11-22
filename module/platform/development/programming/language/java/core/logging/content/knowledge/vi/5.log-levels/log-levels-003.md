# INFO — mức log cho sự kiện vận hành trong Java Core Logging

## 1. INFO là gì?

Trong nhóm kiến thức **Log level**, **INFO** là mức dùng để ghi các sự kiện vận hành bình thường nhưng đủ quan trọng để người phát triển và người vận hành hiểu chương trình đã làm gì và kết quả ra sao. Với Java SE, INFO được biểu diễn bằng hằng **java.util.logging.Level.INFO** của API **java.util.logging (JUL)**.

Ví dụ, ứng dụng có thể ghi INFO khi khởi động thành công, hoàn tất một tác vụ nền, chấp nhận một đơn hàng, hoặc từ chối yêu cầu theo quy tắc nghiệp vụ đã biết. Mục đích của INFO là giữ lại **những mốc có ý nghĩa** mà không cần ghi từng phép tính, từng vòng lặp hay mọi lần gọi hàm.

~~~text
INFO | event=service.ready service=order-service version=1.2.0
INFO | event=order.accepted requestId=req-42 orderId=ord-7
INFO | event=job.completed jobId=job-19 count=250 durationMs=840
~~~

Ba dòng trên minh họa một **định dạng thông điệp do ứng dụng lựa chọn**, không phải đầu ra mặc định của JUL. Một thông điệp INFO có thể mô tả thành công, kết quả trung tính hoặc một **từ chối nghiệp vụ hợp lệ**. Nó không mặc nhiên có nghĩa “không có vấn đề gì”, và cũng không phải lời bảo đảm rằng bản ghi đã được lưu vào nơi lưu trữ cuối cùng.

**Ý nghĩa thực tế:** khi điều tra một yêu cầu, INFO nên giúp trả lời “yêu cầu đã đến bước nào, quyết định quan trọng là gì, kết quả cuối cùng ra sao?”. Những chi tiết chỉ cần khi debug nên để ở FINE/FINER/FINEST hoặc công cụ quan sát phù hợp khác.

## 2. INFO nằm ở đâu trong thang mức JUL?

Các mức chuẩn phổ biến trong JUL, theo ngưỡng từ cao xuống thấp:

| Mức | Giá trị Level.intValue() | Dùng khi nào | Qua ngưỡng Logger = INFO? |
| --- | ---: | --- | --- |
| SEVERE | 1000 | Lỗi nghiêm trọng, thao tác hay thành phần quan trọng thất bại | Có |
| WARNING | 900 | Tình trạng bất thường, suy giảm, cần theo dõi | Có |
| **INFO** | **800** | Mốc vận hành, sự kiện và kết quả nghiệp vụ đáng quan tâm | **Có** |
| CONFIG | 700 | Thông tin cấu hình hữu ích | Không |
| FINE | 500 | Chẩn đoán thông thường | Không |
| FINER | 400 | Chẩn đoán chi tiết hơn | Không |
| FINEST | 300 | Chi tiết rất sâu | Không |

JUL còn có **Level.ALL** để mở ngưỡng cho mọi mức và **Level.OFF** để tắt logging ở thành phần tương ứng. Hệ thống có thể có mức tùy biến, nên bảng mô tả các mức chuẩn của Java.

Khi viết:

~~~java
logger.setLevel(Level.INFO);
~~~

Logger **không chỉ nhận đúng mức INFO**. Về nguyên tắc ngưỡng, nó cho qua INFO và các mức cao hơn như WARNING, SEVERE. Các mức thấp hơn như CONFIG và FINE không qua. Đây chỉ là một bước trong pipeline: **Filter của Logger**, **Handler level**, **Handler Filter** và đầu ra vẫn có thể loại bản ghi.

Ví dụ những lời gọi có mức khác nhau:

~~~java
logger.fine("event=cache.lookup");       // Dưới ngưỡng INFO
logger.info("event=service.ready");      // Đạt ngưỡng
logger.warning("event=backend.slow");    // Đạt ngưỡng
logger.severe("event=storage.failed");   // Đạt ngưỡng
~~~

Các đoạn này là **mẫu sử dụng bên trong mã có sẵn biến logger**, không phải chương trình độc lập.

### Phân biệt INFO với WARNING, SEVERE và FINE

- **INFO:** sự kiện dự kiến xảy ra và có giá trị quan sát, ví dụ **order.accepted** hoặc **order.rejected reasonCode=INVALID_QUANTITY** khi dữ liệu không hợp lệ theo quy tắc.
- **WARNING:** tín hiệu bất thường có nguy cơ ảnh hưởng xử lý, ví dụ dịch vụ phụ thuộc chậm khiến hệ thống retry.
- **SEVERE:** tình trạng lỗi nghiêm trọng, chẳng hạn không thể lưu dữ liệu và yêu cầu thất bại do lỗi hệ thống.
- **FINE:** thông tin phục vụ chẩn đoán chi tiết, như cache hit/miss hay từng bước nội bộ của thuật toán.

Không nên nâng mọi HTTP 4xx hoặc mọi ngoại lệ đã được dự kiến lên WARNING/SEVERE. Chọn level dựa trên **bản chất và tác động** của sự kiện, thay vì nhìn tên Exception hoặc chữ “failed” trong thông điệp.

## 3. Khi nào nên tạo log INFO?

Một log INFO tốt thường đánh dấu **ranh giới xử lý**, **thay đổi trạng thái** hoặc **quyết định nghiệp vụ**.

| Nhóm sự kiện | Mã event minh họa | Trường nên có nếu phù hợp |
| --- | --- | --- |
| Vòng đời dịch vụ | service.started, service.ready | service, version, environment |
| Hoàn tất xử lý nền | job.completed | jobId, outcome, processedCount, durationMs |
| Chấp nhận hành động nghiệp vụ | order.accepted | requestId, orderId, outcome |
| Từ chối theo quy tắc đã biết | order.rejected | requestId, orderId, reasonCode |
| Chuyển trạng thái | shipment.dispatched | shipmentId, oldStatus, newStatus |
| Hoàn thành một đợt nhập dữ liệu | import.completed | batchId, importedCount, rejectedCount |
| Thay đổi cấu hình vận hành quan trọng | mode.switched | component, oldMode, newMode, reasonCode |

Không bắt buộc mỗi nhóm đều phải dùng INFO. Ví dụ nhập dữ liệu diễn ra từng giây có thể cần metric tổng hợp và ít INFO hơn, còn một sự kiện nghiệp vụ hiếm và quan trọng có thể cần ghi rõ để điều tra.

**Ba câu hỏi hữu ích trước khi thêm INFO:**

1. Nếu log này không tồn tại, liệu có khó hiểu trạng thái, kết quả hoặc quyết định quan trọng của hệ thống không?
2. Sự kiện có đủ ý nghĩa để xuất hiện ở môi trường production với lưu lượng thực tế không?
3. Người đọc có thể dựa vào thông điệp và các trường đi kèm để tìm kiếm, liên kết và giải thích nó không?

Nếu câu trả lời phần lớn là “không”, nội dung có thể phù hợp FINE, metric hoặc tracing hơn.

## 4. Những điều không nên ghi ở mức INFO

Không dùng INFO như một lệnh **println()** cho mọi bước xử lý. Những cách làm sau dễ làm giảm giá trị của log:

- Ghi từng lần lặp, biến tạm, kiểm tra điều kiện, thao tác map/filter hoặc truy cập cache có tần suất cao.
- Ghi cùng một sự kiện “request started” tại controller, service và repository khiến người vận hành nhìn thấy ba dòng trùng ý nghĩa.
- Ghi toàn bộ body request/response hoặc dữ liệu nhạy cảm vào log chỉ để tiện debug.
- Ghi stack trace cho một tình huống kiểm tra đầu vào đã được dự kiến và được xử lý bình thường.
- Ghi heartbeat mỗi giây khi hệ thống không có nhu cầu phân tích từng heartbeat riêng biệt.
- Ghi **order.completed** trước khi giao dịch đã thực sự hoàn tất, làm thông điệp mâu thuẫn với trạng thái nếu sau đó rollback.

Trong hệ thống có lưu lượng lớn, việc ghi INFO cho **mỗi yêu cầu HTTP** có thể là mục tiêu đúng của một cơ chế access log, nhưng cần tính chi phí và tránh tạo lại cùng một thông tin ở các lớp khác. INFO không nên trở thành bản sao của tất cả metric hoặc trace.

## 5. Một log INFO hữu ích nên chứa gì?

Ví dụ thông điệp tốt hơn câu “Finished”:

~~~text
INFO event=order.rejected requestId=req-105 orderId=ord-23 outcome=REJECTED reasonCode=INVALID_QUANTITY
~~~

Các thành phần cần xem xét:

- **timestamp:** thời điểm phát sinh; dùng quy ước nhất quán, ưu tiên UTC khi tập trung log.
- **level:** INFO, cùng tên logger hoặc service để biết nguồn phát.
- **event:** tên sự kiện ổn định như order.rejected hoặc job.completed.
- **requestId/correlationId/jobId:** định danh liên kết các bản ghi thuộc cùng luồng.
- **objectId:** mã đối tượng cần thiết và được phép ghi theo chính sách dữ liệu.
- **outcome và reasonCode:** kết quả và nguyên nhân đã chuẩn hóa, thuận tiện cho truy vấn.
- **durationMs, attempt, count:** các số liệu hữu ích trong xử lý nhiều bước.

JUL tự cung cấp thông tin như level, thời điểm và logger name trong LogRecord, nhưng **không tự sinh mã event, requestId hay traceId** cho ứng dụng. Muốn structured logging kiểu JSON, cần formatter/encoder hoặc pipeline tương ứng; bản thân mức INFO không quyết định định dạng dữ liệu.

Tránh chèn dữ liệu do người dùng nhập trực tiếp vào một thông điệp không escape. Dữ liệu có ký tự xuống dòng hoặc điều khiển có thể làm giả dòng log (**log injection**). Không ghi mật khẩu, token, cookie, private key, dữ liệu thẻ, hoặc thông tin cá nhân ngoài nhu cầu hợp lệ.

## 6. Tại sao gọi logger.info() mà không có dòng log?

Với JUL, bản ghi phải đi qua nhiều bước:

~~~text
logger.info(message)
     |
     v
Logger: level hữu hiệu có cho INFO đi qua?
     |-- Không -> kết thúc
     v
Logger: Filter có chấp nhận?
     |-- Không -> kết thúc
     v
Handler A: level và Filter có chấp nhận?
     |-- Có -> Formatter -> console
     |
     +---- Handler B: level và Filter có chấp nhận?
     |          Có -> Formatter -> file
     |
     +---- Handler trên Logger cha (nếu useParentHandlers=true)
                Kiểm tra điều kiện riêng của Handler cha
~~~

**Điều kiện cần hiểu chính xác:**

1. **Logger level:** đặt Logger ở WARNING sẽ chặn INFO. Khi Logger dùng **setLevel(null)**, level hữu hiệu có thể được thừa hưởng từ cây Logger cha.
2. **Logger Filter:** có thể chặn sự kiện INFO cụ thể ngay tại nguồn.
3. **Handler level:** Logger đang ở INFO nhưng Handler ở WARNING thì handler đó vẫn bỏ INFO.
4. **Handler Filter:** có thể bỏ INFO theo event, nguồn phát hoặc ngữ cảnh.
5. **Logger cha:** nếu **useParentHandlers=true**, bản ghi có thể đến những Handler được gắn trên Logger cha. Trong JUL, Filter/level của **các Handler** đó có tác dụng; không giả định Filter ở mọi Logger cha được chạy lại đối với bản ghi đi lên từ Logger con.
6. **Output:** Formatter, stream, file hoặc collector có thể cấu hình khác nhau, gặp lỗi I/O hoặc chưa xả đệm.

Bảng minh họa khi **Logger level = INFO** và không có Filter từ chối:

| Bản ghi | Handler level = ALL | Handler level = INFO | Handler level = WARNING |
| --- | --- | --- | --- |
| FINE | Logger đã chặn | Logger đã chặn | Logger đã chặn |
| INFO | Qua ngưỡng Handler | Qua ngưỡng Handler | Handler chặn |
| WARNING | Qua ngưỡng Handler | Qua ngưỡng Handler | Qua ngưỡng Handler |
| SEVERE | Qua ngưỡng Handler | Qua ngưỡng Handler | Qua ngưỡng Handler |

“Qua ngưỡng” chưa bảo đảm được lưu: Filter và khả năng ghi ra đích vẫn cần kiểm tra.

## 7. Ví dụ Java 17+ chạy độc lập

Chương trình sau minh họa:

- Logger nhận từ INFO trở lên.
- Handler ban đầu nhận tất cả mức đã tới nó.
- FINE bị Logger chặn; INFO và WARNING xuất hiện.
- Sau khi Handler đổi thành WARNING, INFO không còn xuất dù Logger vẫn cho phép.
- Thông điệp JUL dùng tham số **{0}**, **{1}** sẽ được Formatter thay đúng vị trí.

Tạo tệp **InfoLevelDemo.java** với toàn bộ mã sau:

~~~java
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class InfoLevelDemo {
    private static final Logger LOG =
            Logger.getLogger("examples.logging.info");

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        Handler output = new StreamHandler(System.out, new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + " | " + formatMessage(record)
                        + System.lineSeparator();
            }
        }) {
            @Override
            public synchronized void publish(LogRecord record) {
                super.publish(record);
                flush();
            }
        };

        output.setLevel(Level.ALL);
        LOG.addHandler(output);

        try {
            LOG.fine("event=cache.lookup");
            LOG.info("event=service.started service=catalog");
            LOG.log(Level.INFO,
                    "event=order.accepted orderId={0} quantity={1}",
                    new Object[] {"ord-7", 2});
            LOG.warning("event=inventory.slow dependency=stock");

            output.setLevel(Level.WARNING);
            LOG.info("event=order.completed status=OK");
            LOG.warning("event=dependency.retry dependency=stock");
        } finally {
            LOG.removeHandler(output);
            output.flush();
        }
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac InfoLevelDemo.java
java InfoLevelDemo
~~~

**Stdout chính xác:**

~~~text
INFO | event=service.started service=catalog
INFO | event=order.accepted orderId=ord-7 quantity=2
WARNING | event=inventory.slow dependency=stock
WARNING | event=dependency.retry dependency=stock
~~~

### Giải thích từng bước

1. **LOG.setUseParentHandlers(false)** giúp bản ghi không đi thêm tới các Handler của Logger cha, tránh đầu ra trùng do cấu hình môi trường.
2. **LOG.setLevel(Level.INFO)** khiến LOG.fine(...) không được chuyển xuống Handler.
3. **output.setLevel(Level.ALL)** cho phép Handler nhận INFO và WARNING đã qua Logger trong giai đoạn đầu.
4. **LOG.info(...)** tạo log INFO đầu tiên. **LOG.log(Level.INFO, ...)** tạo log thứ hai và truyền mảng tham số.
5. Formatter gọi **formatMessage(record)** nên thay **{0} → ord-7** và **{1} → 2**. Đây là cú pháp tham số JUL dùng MessageFormat, không phải cú pháp **{}** của SLF4J.
6. WARNING đầu tiên cũng được xuất vì WARNING có giá trị mức cao hơn INFO.
7. **output.setLevel(Level.WARNING)** chuyển ngưỡng Handler. Sau đó **LOG.info("event=order.completed...")** bị Handler bỏ, còn WARNING cuối cùng được xuất.
8. **StreamHandler(System.out, Formatter)** dùng stdout và một định dạng cố định để đầu ra không phụ thuộc múi giờ, ngôn ngữ hoặc định dạng SimpleFormatter mặc định. **ConsoleHandler mặc định của JUL thường ghi ra stderr**.
9. Override **publish()** rồi gọi **flush()** giúp đẩy bản ghi ra stdout ngay. Chương trình không đóng Handler gắn với System.out, vì việc đóng StreamHandler có thể đóng cả luồng stdout.

Bảng quyết định tương ứng:

| Lời gọi | Logger level = INFO | Handler trước/sau đổi level | Kết quả |
| --- | --- | --- | --- |
| FINE cache.lookup | Chặn | Không tới Handler | Không xuất |
| INFO service.started | Cho qua | ALL | Xuất |
| INFO order.accepted | Cho qua | ALL | Xuất |
| WARNING inventory.slow | Cho qua | ALL | Xuất |
| INFO order.completed | Cho qua | WARNING | Không xuất |
| WARNING dependency.retry | Cho qua | WARNING | Xuất |

Đây là ví dụ tối giản phục vụ học tập. Trong hệ thống thực, nên sử dụng cấu hình logging thống nhất của ứng dụng và có chính sách thu thập log.

## 8. Những cách ghi INFO thường dùng trong JUL

### A. Phương thức info(String)

~~~java
logger.info("event=job.completed jobId=job-19 outcome=SUCCESS");
~~~

Dùng khi thông điệp ngắn, rẻ để tạo và rõ nghĩa. Đoạn minh họa giả định đã có biến **logger** kiểu **java.util.logging.Logger**.

### B. Phương thức log(Level.INFO, message)

~~~java
logger.log(Level.INFO, "event=service.ready service=catalog");
~~~

Dùng khi cần một cách gọi API thống nhất cho nhiều mức. Phải import **java.util.logging.Level**.

### C. Tham số được đánh số kiểu JUL

~~~java
logger.log(Level.INFO,
        "event=order.accepted orderId={0} quantity={1}",
        new Object[] {orderId, quantity});
~~~

Nếu Formatter dùng **formatMessage(record)**, tham số được đưa vào thông điệp bằng **MessageFormat**. Không dùng sai cú pháp placeholder **{}** vốn thường gặp ở SLF4J. Mã trên là snippet, giả định **orderId** và **quantity** đã tồn tại.

### D. Trì hoãn tạo thông điệp bằng Supplier

~~~java
logger.info(() -> "event=batch.completed batchId=" + batchId
        + " processedCount=" + processedCount);
~~~

Overload **info(Supplier<String>)** có từ Java 8. Nếu **Logger** chặn INFO theo ngưỡng, nó không cần gọi Supplier để xây thông điệp. Tuy nhiên nếu Logger chấp nhận nhưng **Handler** chặn, Supplier có thể đã được đánh giá trước khi Handler lọc. Lazy message không thay thế được thiết kế level/Filter/Handler hiệu quả.

### E. Tự bảo vệ một phép tính nặng

~~~java
if (logger.isLoggable(Level.INFO)) {
    logger.info(createExpensiveSummary());
}
~~~

**isLoggable(Level.INFO)** hữu ích nếu tính toán để tạo thông điệp tốn chi phí. Điều kiện này kiểm tra khả năng log theo ngưỡng Logger, **không bảo đảm** bản ghi được ghi ra Handler. Với chuỗi đơn giản, Supplier thường thuận tiện hơn.

Các mẫu A–E là những đoạn mã nằm trong ngữ cảnh ứng dụng đã khai báo biến cần thiết, không phải tệp Java độc lập. Chương trình hoàn chỉnh ở mục 7 là ví dụ có thể dùng trực tiếp.

## 9. Cấu hình ngưỡng INFO trong Java

Có hai cách phổ biến:

**Qua mã:**

~~~java
Logger ordersLogger = Logger.getLogger("com.example.orders");
ordersLogger.setLevel(Level.INFO);
~~~

Khi đó Logger có ngưỡng INFO, còn mỗi Handler vẫn áp dụng mức và Filter riêng. Đây là snippet cần import Logger và Level.

**Qua LogManager và tệp logging.properties**, ví dụ:

~~~properties
handlers=java.util.logging.ConsoleHandler
.level=INFO
java.util.logging.ConsoleHandler.level=INFO
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter
~~~

Chạy một ứng dụng có lớp chính **com.example.Main** và dùng cấu hình JUL:

~~~bash
java -Djava.util.logging.config.file=logging.properties com.example.Main
~~~

Câu lệnh là **mẫu cho ứng dụng có lớp com.example.Main**, không phải lệnh chạy ví dụ InfoLevelDemo. Trong **InfoLevelDemo**, mã cố ý thiết lập Logger/Handler riêng và tắt Handler của Logger cha để có stdout xác định; vì thế cấu hình ConsoleHandler của Logger gốc trong tệp properties không phải nơi quyết định đầu ra demo đó.

Ghi nhớ:

- **.level=INFO** là cấu hình level của Logger gốc; một Logger chưa tự đặt level có thể thừa hưởng mức hữu hiệu từ cha.
- **java.util.logging.ConsoleHandler.level=INFO** cấu hình level riêng của ConsoleHandler, cần xem xét bên cạnh ngưỡng Logger.
- LogManager đọc cấu hình tại thời điểm khởi tạo. Cấu hình chương trình hoặc framework có thể ghi đè một số thuộc tính.
- ConsoleHandler thường xuất ra **System.err**, không phải System.out, và SimpleFormatter có thông tin ngữ cảnh khác ví dụ tự viết.
- Với ứng dụng dùng module khai báo tường minh, mã phụ thuộc JUL cần **requires java.logging;** trong module-info.java:

~~~java
module com.example.app {
    requires java.logging;
}
~~~

Đoạn module-info.java chỉ minh họa khi dùng JPMS; chương trình Java đơn tệp ở mục 7 không cần tạo file này.

## 10. INFO trong hệ thống đồng thời, đa dịch vụ và nhiều đầu ra

Ở ứng dụng nhiều request, log INFO của những yêu cầu khác nhau có thể xen kẽ. Một dòng INFO đơn lẻ cần có định danh liên kết:

~~~text
INFO event=order.received requestId=req-42
INFO event=order.received requestId=req-43
INFO event=order.accepted requestId=req-42 orderId=ord-7
INFO event=order.rejected requestId=req-43 reasonCode=INVALID_QUANTITY
~~~

Thứ tự log không nhất thiết khẳng định hai request có quan hệ nhân quả. **requestId/correlationId** giúp lọc các bản ghi của một yêu cầu; với tác vụ nền, sử dụng **jobId/messageId** phù hợp.

Khi một yêu cầu chuyển sang Executor, CompletableFuture, virtual thread hoặc dịch vụ khác, context cần được **truyền và dọn** theo đúng cơ chế. Không được giả định **ThreadLocal** hay **MDC** tự lan qua mọi ranh giới bất đồng bộ. JUL nguyên bản không tự gắn traceId/spanId; nếu có OpenTelemetry hoặc framework logging, cần tích hợp context đúng cách.

Một Logger có thể có nhiều Handler: console cho sự kiện vận hành và file cho lưu trữ chẩn đoán, chẳng hạn. Handler A có ngưỡng INFO, Handler B có ngưỡng WARNING; cùng bản ghi INFO có thể chỉ được xuất ở A. Nếu chỉ cần loại một loại sự kiện khỏi console, hãy đặt Filter trên Handler console, tránh đặt Filter trên Logger nguồn làm các Handler khác cùng mất log.

## 11. INFO, metric, tracing và audit log khác nhau thế nào?

| Công cụ | Trả lời tốt nhất | Ví dụ |
| --- | --- | --- |
| INFO/application log | Diễn biến và kết quả cụ thể của một sự kiện | order.rejected với requestId, reasonCode |
| Access log | Thông tin yêu cầu HTTP tại biên server/proxy | method, route, status, latency |
| Metric | Tần suất, tỷ lệ và xu hướng tổng hợp | Số request, tỷ lệ lỗi, p95 latency |
| Distributed tracing | Đường đi và thời gian qua các span/dịch vụ | Request chậm ở dịch vụ kho hay database |
| Audit log | Bằng chứng hành động có yêu cầu toàn vẹn và phân quyền | Ai thay đổi quyền hoặc duyệt giao dịch |

Không nên biến INFO thành nơi lưu **tất cả** dữ liệu quan sát. Metric thường phù hợp đo tần suất cao và SLO; tracing giúp giải thích đường đi. Audit log có thể có yêu cầu pháp lý và khả năng chống sửa đổi riêng, nên **không mặc nhiên** được thay bằng INFO thông thường. Với hệ thống có yêu cầu kiểm toán, không được tùy tiện lấy mẫu hoặc tắt các sự kiện bắt buộc.

## 12. Bảo mật và kiểm soát chi phí khi bật INFO

INFO thường xuyên được bật ở production. Do đó, mức INFO cần được quản lý như một phần của thiết kế hệ thống:

1. **Giảm dữ liệu ngay tại nguồn:** không ghi token, password, session cookie, khóa API, bí mật giao dịch hoặc body nhạy cảm.
2. **Chọn ID phù hợp:** requestId, jobId, orderId chỉ ghi khi cần; tuân thủ chính sách dữ liệu nếu ID có thể liên kết với cá nhân.
3. **Chuẩn hóa event:** dùng tên ổn định như job.completed và reasonCode thay cho chuỗi người dùng nhập tùy ý.
4. **Chống log injection:** escape ký tự xuống dòng và ký tự điều khiển khi phải xuất dữ liệu chưa tin cậy; dùng formatter/encoder có quy ước rõ.
5. **Quản lý volume:** không ghi INFO trong vòng lặp nóng; tổng hợp số lượng và duration khi có thể.
6. **Hiểu tính bất đồng bộ:** pipeline logger/collector có thể đệm và mất bản ghi khi dừng đột ngột; level INFO không tạo cam kết lưu bền.
7. **Quy định retention và quyền đọc:** xác định thời hạn lưu, ai được truy cập, khả năng tra cứu và chi phí ingest/long-term storage.
8. **Thử trên tải thực:** nếu thêm INFO cho mỗi request, đo lượng bản ghi và CPU/I/O, xác minh không ảnh hưởng đáng kể tới luồng nghiệp vụ.

Ví dụ trong một job xử lý một triệu phần tử, thay vì INFO cho mỗi phần tử, chỉ cần INFO ở **job.started** và **job.completed** với **processedCount**, **failedCount**, **durationMs**; các chi tiết từng phần tử có thể dùng FINE/DEBUG có kiểm soát hoặc cơ chế xử lý lỗi chuyên biệt.

## 13. Lỗi phổ biến khi làm việc với INFO

| Vấn đề | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Gọi info() nhưng không thấy log | Logger ở WARNING/SEVERE hoặc thừa hưởng mức cao | Kiểm tra level hữu hiệu của Logger |
| INFO bị mất dù Logger ở INFO | Handler ở WARNING hoặc Filter chặn | Kiểm tra Handler level và Filter |
| INFO xuất hai lần | Handler tại Logger và Logger cha cùng nhận | Kiểm tra useParentHandlers và danh sách Handler |
| Test không thấy stdout | ConsoleHandler JUL thường ghi stderr | Kiểm tra stderr, hoặc tạo StreamHandler(System.out) cho demo |
| Placeholder {0} không được thay | Formatter không gọi formatMessage, sai parameters hoặc dùng nhầm API | Dùng JUL log(Level, String, Object[]) và Formatter phù hợp |
| INFO tràn ngập trong production | Ghi quá chi tiết hoặc lặp ở nhiều tầng | Chỉ ghi sự kiện có ý nghĩa; dùng FINE/metric |
| Mất liên kết giữa các dòng | Thiếu requestId/jobId hoặc không truyền context | Truyền correlation context đúng qua luồng và dịch vụ |
| Bản ghi chứa dữ liệu nhạy cảm | Log toàn bộ object, payload hoặc exception message | Giảm/che dữ liệu tại nguồn và cấu hình encoder |
| INFO báo hoàn tất rồi giao dịch rollback | Log kết quả trước thời điểm xác nhận | Chuyển log tới điểm commit/thành công phù hợp |
| Đổi cấu hình nhưng mức INFO không đổi | Chưa tải đúng logging.properties, dùng backend khác hoặc code ghi đè | Kiểm tra backend thực tế và cấu hình khi chạy |

**Lưu ý về framework:** SLF4J là facade, Logback/Log4j 2 là các backend phổ biến. Chúng cũng có INFO nhưng API và cú pháp tham số có thể khác JUL. Ví dụ **logger.info("orderId={}", id)** thuộc phong cách SLF4J, còn JUL dùng **{0}** với tham số theo MessageFormat. Một ứng dụng dùng SLF4J + Logback cần xem level/Filter/Appender thật sự của backend, không sửa JUL rồi mặc định rằng log sẽ thay đổi.

## 14. Checklist sử dụng INFO cho một sự kiện mới

1. Sự kiện này thể hiện **trạng thái, quyết định, kết quả hoặc ranh giới vận hành** thực sự quan trọng?
2. Nếu đây là bất thường, WARNING/SEVERE có phù hợp hơn không? Nếu là thông tin chẩn đoán từng bước, FINE có phù hợp hơn không?
3. Event name, outcome và reasonCode có ổn định để tìm kiếm giữa các phiên bản?
4. Có **requestId/jobId** và dữ liệu ngữ cảnh cần thiết, không mang thông tin nhạy cảm?
5. Lưu lượng INFO dự kiến có phù hợp chi phí CPU, I/O và lưu trữ?
6. **Logger level**, **Logger Filter**, **Handler level**, **Handler Filter** và collector có cùng hỗ trợ việc ghi bản ghi này?
7. Khi thử nhánh thành công, từ chối hợp lệ và lỗi kỹ thuật, log có giúp phân biệt ba kết quả không?

**Kết luận:** **Level.INFO** là mức ghi nhận các mốc vận hành bình thường nhưng có giá trị trong Java Logging. Hiểu rõ INFO trong pipeline **Logger → Filter → Handler → Formatter/đầu ra**, ghi sự kiện có ngữ cảnh và kiểm soát chi phí sẽ giúp log trở thành nguồn thông tin hữu ích để vận hành và điều tra vấn đề.
