# Bảo vệ dữ liệu nhạy cảm và kiểm soát overhead khi thu thập chẩn đoán

Trong Java 21, các công cụ quan sát runtime như Java Flight Recorder (JFR), logging, JMX, thread dump, heap dump và GC log giúp tìm nguyên nhân sự cố. Tuy nhiên, dữ liệu chẩn đoán có thể chứa thông tin nhạy cảm hoặc làm tăng tải nếu thu thập quá rộng, ghi quá lâu hay lưu trữ thiếu kiểm soát.

Một quy trình chẩn đoán an toàn cần trả lời hai câu hỏi: dữ liệu nào thực sự cần để điều tra và chi phí của việc thu thập dữ liệu đó là bao nhiêu? Hãy giảm dữ liệu ngay từ nguồn, giới hạn phạm vi và thời gian thu thập, bảo vệ artifact sau khi tạo, rồi chỉ cấp quyền truy cập cho người cần thiết.

## 1. Dữ liệu chẩn đoán có thể tiết lộ điều gì?

Không chỉ log ứng dụng mới có nguy cơ chứa dữ liệu nhạy cảm. Mỗi loại artifact có thể tiết lộ một phần khác nhau của môi trường và dữ liệu đang chạy.

| Nguồn chẩn đoán | Dữ liệu có thể xuất hiện | Rủi ro |
|---|---|---|
| Application log | User ID, email, request path, query string, nội dung lỗi, token bị ghi nhầm | Lộ dữ liệu cá nhân, credential hoặc nghiệp vụ |
| JFR recording | Stack trace, thread name, class/method, socket metadata, custom event fields, thông tin môi trường | Tiết lộ cấu trúc ứng dụng, host, endpoint hoặc dữ liệu do ứng dụng tự ghi vào event |
| Heap dump | Object graph, chuỗi trong heap, request/response, session, access token, khóa hoặc dữ liệu người dùng còn trong bộ nhớ | Có thể chứa lượng lớn dữ liệu nhạy cảm ở dạng có thể khôi phục |
| Thread dump | Thread name, stack trace, class name, lock/monitor và thông tin trạng thái thread | Tiết lộ cấu trúc xử lý, tên dịch vụ, đường dẫn hoặc định danh được đưa vào thread name |
| GC log | Thời điểm GC, dung lượng heap, pause, tên collector và thông tin runtime | Tiết lộ mô hình tải, kích thước dữ liệu và nhịp hoạt động |
| JMX/MBean | Runtime arguments, system properties, thread/heap metrics, thông tin MBean và thao tác quản trị | Có thể lộ cấu hình hoặc mở quyền điều khiển runtime nếu endpoint bị truy cập trái phép |
| Core dump | Trạng thái bộ nhớ tiến trình tại thời điểm dump | Có thể chứa secret, dữ liệu heap và thông tin nhạy cảm khác |

Một heap dump có thể chứa chuỗi dữ liệu ứng dụng đang giữ trong bộ nhớ. Ví dụ, access token, nội dung request, mật khẩu tạm thời hoặc dữ liệu cá nhân có thể còn tồn tại trong object graph. Thread dump thường tập trung vào stack và trạng thái đồng bộ, không phải bản chụp giá trị mọi local variable; tuy vậy, tên thread, tên class, stack frame và lock metadata vẫn có thể tiết lộ thông tin nội bộ.

Hãy xem artifact chẩn đoán của production là dữ liệu cần bảo vệ, ngay cả khi công cụ tạo ra nó được cung cấp bởi JDK.

## 2. Phân loại dữ liệu trước khi bật thu thập

Trước khi bật một event, thêm log field hoặc tạo dump, xác định dữ liệu thuộc nhóm nào:

- **Thông tin vận hành:** thời gian xử lý, số lượng request, trạng thái thành công/thất bại, kích thước queue.
- **Thông tin định danh nội bộ:** service name, hostname, thread name, tenant ID, user ID, key ID.
- **Dữ liệu cá nhân hoặc nghiệp vụ:** email, số điện thoại, địa chỉ, nội dung giao dịch, request body.
- **Bí mật xác thực:** password, access token, refresh token, cookie, API key, private key, session secret.

Chỉ thu thập trường tối thiểu để trả lời câu hỏi vận hành. Ví dụ, khi điều tra endpoint chậm, thường cần route template, status class, duration và trace ID; không cần ghi toàn bộ URL có query string, request body hoặc authorization header.

Không ghi bí mật vào log, JFR event, thread name, system property hoặc tên file. Tránh truyền secret qua command line như `-Dapi.password=...`, vì command line có thể xuất hiện trong process inspection hoặc runtime diagnostics. Dùng secret manager, keystore hoặc cơ chế cấp secret phù hợp với nền tảng triển khai.

Nếu cần liên kết nhiều sự kiện, dùng correlation ID ngẫu nhiên hoặc định danh đã được token hóa. Không dùng access token, email hoặc dữ liệu cá nhân làm correlation ID.

## 3. Logging an toàn: giảm dữ liệu ngay từ nguồn

Logging nên ghi lại sự kiện và kết quả xử lý, không sao chép toàn bộ input của người dùng. Một bản ghi hữu ích thường gồm:

- Timestamp và severity.
- Tên operation hoặc route template đã được chuẩn hóa.
- Kết quả ở mức phân loại, chẳng hạn success, validation_error, timeout.
- Duration và các số đo cần thiết.
- Correlation ID không chứa thông tin xác thực.
- Mã lỗi ổn định thay cho nội dung exception có thể chứa dữ liệu đầu vào.

Ví dụ dùng `System.Logger` của JDK với các trường đã được kiểm soát:

~~~java
public final class RequestLogging {
    private static final System.Logger LOG =
            System.getLogger(RequestLogging.class.getName());

    static void completed(
            String operation,
            String outcome,
            long durationMillis,
            String correlationId
    ) {
        LOG.log(
                System.Logger.Level.INFO,
                "operation={0}, outcome={1}, durationMs={2}, correlationId={3}",
                operation,
                outcome,
                durationMillis,
                correlationId
        );
    }
}
~~~

Trong ví dụ, `operation` và `outcome` nên đến từ tập giá trị được phép, còn `correlationId` phải được tạo theo chính sách không chứa PII hoặc secret. Không đưa raw URL, query string, request body, cookie hoặc authorization header vào các tham số này.

### Redaction và chuẩn hóa

Nếu nghiệp vụ bắt buộc ghi một định danh, hãy cân nhắc:

- Thay bằng token định danh nội bộ không thể đảo ngược trong hệ thống log.
- Chỉ ghi một phần giá trị khi đủ cho việc đối chiếu.
- Áp dụng allowlist field thay vì cố gắng blacklist mọi trường nhạy cảm.
- Chuẩn hóa ký tự điều khiển để ngăn log injection.
- Không ghi nội dung exception nguyên văn nếu exception có thể nhúng dữ liệu người dùng hoặc secret.

Redaction ở tầng xử lý log cuối cùng không phải lúc nào cũng đủ. Dữ liệu gốc có thể đã đi qua queue bất đồng bộ, buffer hoặc hệ thống trung chuyển. Tốt nhất là không đưa dữ liệu nhạy cảm vào log event ngay từ đầu.

### Retention và quyền truy cập log

Log production nên có:

- Quyền đọc giới hạn theo vai trò.
- Mã hóa khi truyền và khi lưu nếu hạ tầng hỗ trợ.
- Retention theo mục đích điều tra và yêu cầu lưu trữ.
- Rotation theo dung lượng/thời gian để tránh đầy đĩa.
- Audit trail cho việc truy cập hoặc xuất dữ liệu nhạy cảm.
- Quy trình xóa an toàn theo chính sách khi hết hạn.

Không gửi log production sang máy cá nhân hoặc kênh chia sẻ công khai để tiện điều tra. Khi cần chia sẻ, tạo bản đã lọc/redact và kiểm tra nội dung trước khi chuyển.

## 4. JFR: thu thập sâu nhưng có giới hạn

Java Flight Recorder là công cụ profiling và diagnostics tích hợp trong JDK. JFR có thể ghi event về JVM, garbage collection, thread, class loading, execution sample, lock contention và các event do ứng dụng định nghĩa.

JFR được thiết kế để có overhead thấp trong nhiều cấu hình production, nhưng không có nghĩa overhead bằng không. Cấu hình event, tần suất, stack trace, thời gian recording và tải ghi file đều ảnh hưởng tới chi phí.

JDK cung cấp hai cấu hình thường dùng:

| Cấu hình | Mục đích | Đặc điểm |
|---|---|---|
| `default.jfc` / `settings=default` | Theo dõi liên tục hoặc thu thập ban đầu | Ít chi tiết hơn, thường có overhead thấp hơn |
| `profile.jfc` / `settings=profile` | Điều tra sâu hơn trong khoảng thời gian giới hạn | Thu thập nhiều chi tiết hơn và có thể tốn overhead hơn |

Hãy bắt đầu bằng cấu hình `default` cho recording dài hạn. Chỉ dùng `profile` hoặc bật thêm event/stack trace khi có câu hỏi điều tra cụ thể. Đo overhead trên workload gần production trước khi triển khai cấu hình tùy chỉnh rộng.

### Bắt đầu recording có thời hạn bằng jcmd

Có thể điều khiển JFR của một JVM đang chạy bằng `jcmd`:

~~~text
jcmd <pid> JFR.check
jcmd <pid> JFR.start name=incident settings=default duration=5m filename=/secure/diagnostics/incident.jfr maxage=30m maxsize=256m
~~~

Trong ví dụ:

- `<pid>` là process ID của JVM cần điều tra.
- `settings=default` chọn cấu hình mặc định.
- `duration=5m` giới hạn thời gian recording.
- `filename` chỉ tới thư mục chẩn đoán đã được bảo vệ.
- `maxage` và `maxsize` giới hạn tuổi và dung lượng recording lưu trên đĩa.

Các tùy chọn cần được kiểm tra theo loại recording và phiên bản JDK đang chạy. Dung lượng và thời gian ở ví dụ chỉ là giá trị minh họa; chọn theo tốc độ phát sinh event và ngân sách lưu trữ.

Có thể kiểm tra recording, dump dữ liệu hoặc dừng recording:

~~~text
jcmd <pid> JFR.check
jcmd <pid> JFR.dump name=incident filename=/secure/diagnostics/incident-snapshot.jfr
jcmd <pid> JFR.stop name=incident
~~~

Sau khi thu thập, dùng công cụ `jfr` để xem tổng quan hoặc lọc event:

~~~text
jfr summary /secure/diagnostics/incident.jfr
jfr print --events jdk.GarbageCollection,jdk.ExecutionSample /secure/diagnostics/incident.jfr
~~~

Chỉ trích xuất các event cần thiết. Một bản recording đầy đủ có thể chứa stack trace, tên thread, tên class, địa chỉ hoặc metadata môi trường; hãy áp dụng cùng chính sách phân loại và bảo vệ như với log.

## 5. Chọn event và stack trace theo câu hỏi điều tra

Không bật mọi event với stack trace chỉ vì muốn có dữ liệu đầy đủ. Hãy bắt đầu từ câu hỏi:

| Câu hỏi | Dữ liệu có thể cần |
|---|---|
| Có GC pause bất thường không? | Garbage collection, GC phase và pause duration |
| Thread đang tiêu tốn CPU ở đâu? | Execution samples và stack trace phù hợp |
| Có lock contention không? | Java monitor/lock events và thời gian chờ |
| Có allocation pressure không? | Allocation events với ngưỡng và sampling phù hợp |
| Task chờ I/O lâu ở đâu? | Socket/file I/O duration và event liên quan, tùy mức hỗ trợ |
| Ứng dụng xử lý request nào chậm? | Custom event chứa operation đã chuẩn hóa, duration và outcome |

Stack trace hữu ích khi cần xác định call path nhưng làm tăng kích thước recording và chi phí thu thập/ghi. Các event tần suất cao có thể tạo lượng dữ liệu lớn, đặc biệt khi bật stack trace cho mọi occurrence.

Có thể cấu hình event bằng JFR settings hoặc custom configuration. Nên đặt threshold, period, stack trace và enabled state theo câu hỏi cụ thể. Không ghi payload, token, nội dung SQL có dữ liệu nhạy cảm hoặc URL đầy đủ vào event.

## 6. Custom JFR event: chỉ ghi trường đã được cho phép

Ứng dụng có thể định nghĩa event riêng bằng API `jdk.jfr`. Event nên ghi các số đo vận hành và giá trị đã chuẩn hóa, không ghi raw request hoặc dữ liệu xác thực.

~~~java
import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.StackTrace;

@Name("com.example.RequestSummary")
@Label("Request summary")
@Category({"Application", "Requests"})
@StackTrace(false)
final class RequestSummaryEvent extends Event {
    @Label("Operation")
    String operation;

    @Label("Outcome")
    String outcome;

    @Label("Duration in milliseconds")
    long durationMillis;
}

final class RequestMetrics {
    static void record(
            String operation,
            String outcome,
            long durationMillis
    ) {
        RequestSummaryEvent event = new RequestSummaryEvent();

        if (!event.shouldCommit()) {
            return;
        }

        event.operation = allowlistedOperation(operation);
        event.outcome = allowlistedOutcome(outcome);
        event.durationMillis = durationMillis;
        event.commit();
    }

    private static String allowlistedOperation(String value) {
        return switch (value) {
            case "create-order", "get-order", "cancel-order" -> value;
            default -> "other";
        };
    }

    private static String allowlistedOutcome(String value) {
        return switch (value) {
            case "success", "timeout", "rejected", "failure" -> value;
            default -> "other";
        };
    }
}
~~~

Ví dụ dùng `shouldCommit()` để bỏ qua việc gán và commit khi event không được bật hoặc không cần ghi theo cấu hình hiện tại. `@StackTrace(false)` tắt stack trace cho event này, giúp giảm lượng dữ liệu và tránh thu thập call path không cần thiết.

Các nguyên tắc cho custom event:

- Chỉ thêm field có mục đích vận hành rõ ràng.
- Dùng enum hoặc allowlist thay cho raw string từ request.
- Không ghi access token, session ID bí mật, request body, email hoặc dữ liệu thanh toán.
- Không đưa exception message nguyên văn vào field.
- Đặt tên event ổn định và có namespace riêng.
- Đo overhead nếu event được commit với tần suất cao.

JFR event là một kênh lưu dữ liệu. Việc event chỉ được bật trong một recording ngắn không làm cho dữ liệu nhạy cảm trở nên an toàn; file recording vẫn phải được bảo vệ.

## 7. Heap dump: artifact có mức nhạy cảm cao

Heap dump ghi lại object graph của heap tại thời điểm thu thập. Đây là một trong những artifact có nguy cơ lộ dữ liệu cao nhất vì có thể chứa object và chuỗi do ứng dụng giữ.

Có thể tạo heap dump bằng `jcmd`:

~~~text
jcmd <pid> GC.heap_dump /secure/diagnostics/heap.hprof
~~~

Có thể cấu hình JVM tạo heap dump khi gặp OutOfMemoryError:

~~~text
-XX:+HeapDumpOnOutOfMemoryError
-XX:HeapDumpPath=/secure/diagnostics
~~~

Lưu ý:

- Heap dump có thể rất lớn; cần kiểm tra dung lượng đĩa trước khi bật.
- Việc tạo dump có thể làm ứng dụng tạm dừng hoặc giảm throughput đáng kể tùy heap size, collector và môi trường.
- Dump có thể chứa dữ liệu nhạy cảm vẫn còn trong heap.
- Chỉ người được ủy quyền mới được đọc hoặc sao chép file.
- Không gửi dump qua kênh chat, ticket hoặc kho file dùng chung nếu chưa có quy trình bảo vệ.
- Xác định retention và cách xóa sau khi điều tra.

Không nên tạo heap dump theo lịch dày đặc chỉ để quan sát thường xuyên. Dùng metrics, JFR và GC logs trước; chỉ tạo heap dump khi cần phân tích object retention, memory leak hoặc OutOfMemoryError và đã có kế hoạch lưu trữ an toàn.

## 8. Thread dump và chẩn đoán virtual thread

Thread dump giúp điều tra deadlock, lock contention, thread bị block hoặc task không tiến triển. Nội dung có thể tiết lộ thread name, stack trace, class/method, monitor và lock đang chờ.

Với Java 21, `jcmd` có lệnh dump thread hỗ trợ cả virtual thread:

~~~text
jcmd <pid> Thread.dump_to_file -format=json /secure/diagnostics/threads.json
~~~

Có thể dùng định dạng text nếu phù hợp:

~~~text
jcmd <pid> Thread.dump_to_file -format=text /secure/diagnostics/threads.txt
~~~

Định dạng JSON hữu ích cho công cụ phân tích tự động. Tuy nhiên, một ứng dụng tạo rất nhiều virtual thread có thể sinh thread dump rất lớn. Việc dump cũng cần CPU, bộ nhớ và I/O để thu thập/ghi dữ liệu; không nên kích hoạt liên tục trong vòng giám sát ngắn.

Thread dump thường không chứa giá trị của mọi local variable, nhưng vẫn cần bảo vệ vì stack, tên thread và lock metadata có thể tiết lộ tên người dùng, tenant, endpoint, cấu trúc hệ thống hoặc thông tin nội bộ nếu ứng dụng đưa chúng vào tên thread.

## 9. GC log và unified logging

Java 21 dùng unified logging với tùy chọn `-Xlog`. Ví dụ bật GC và safepoint log có rotation:

~~~text
-Xlog:gc*,safepoint:file=/secure/logs/gc.log:time,uptime,level,tags:filecount=5,filesize=20M
~~~

Trong ví dụ:

- `gc*` thu thập nhóm event GC.
- `safepoint` ghi thông tin safepoint.
- `time`, `uptime`, `level`, `tags` là các decorator.
- `filecount=5` và `filesize=20M` giới hạn số file và kích thước mỗi file theo cơ chế rotation.

GC log thường ít nhạy cảm hơn heap dump, nhưng vẫn có thể tiết lộ thời điểm hoạt động, kích thước heap, workload và cấu hình runtime. Lưu ở thư mục có quyền truy cập phù hợp và kiểm soát retention.

Không bật mọi tag ở mức trace trong production nếu chưa đánh giá lượng dữ liệu và overhead. Bắt đầu từ tag cần thiết, mở rộng khi có câu hỏi điều tra cụ thể.

## 10. JMX: bảo vệ kênh quản trị và MBean

JMX cung cấp khả năng quan sát và quản lý JVM thông qua MBean. Remote JMX có thể cho phép đọc metrics, xem runtime information và thực hiện một số thao tác quản trị. Vì vậy, endpoint JMX phải được xem như một giao diện quản trị nhạy cảm.

Khi bật remote JMX, cấu hình xác thực và TLS rõ ràng. Các thuộc tính thường dùng của management agent gồm:

~~~text
-Dcom.sun.management.jmxremote.port=7091
-Dcom.sun.management.jmxremote.authenticate=true
-Dcom.sun.management.jmxremote.ssl=true
-Dcom.sun.management.jmxremote.password.file=/secure/jmx/jmxremote.password
-Dcom.sun.management.jmxremote.access.file=/secure/jmx/jmxremote.access
~~~

Các giá trị trên chỉ là ví dụ cấu hình. Hãy tham khảo tài liệu JDK 21 và chính sách vận hành để thiết lập RMI port, certificate, password/access file, quyền file và firewall phù hợp với môi trường.

Nguyên tắc bảo vệ:

- Không mở JMX trực tiếp ra Internet.
- Giới hạn truy cập bằng network policy, firewall hoặc tunnel quản trị.
- Bật authentication và TLS theo cấu hình được hỗ trợ.
- Dùng tài khoản có quyền tối thiểu; chỉ cấp quyền ghi/thao tác khi thực sự cần.
- Bảo vệ password file bằng quyền filesystem chặt chẽ.
- Không đưa password, token hoặc private key vào MBean attribute.
- Audit các phiên truy cập và thao tác quản trị.
- Ưu tiên local management hoặc kênh quản trị được bảo vệ khi không cần remote access.

Một MBean tự định nghĩa cũng cần xem xét dữ liệu trả về. Không expose system properties chứa secret hoặc object nhạy cảm chỉ để thuận tiện debug.

## 11. Giảm overhead bằng sampling, threshold và giới hạn thời gian

Overhead đến từ nhiều nguồn: instrument event, lấy stack trace, đồng bộ giữa thread, ghi file, serialize dữ liệu và tải xử lý của công cụ phân tích.

Các biện pháp kiểm soát:

1. Bắt đầu với JFR `default` hoặc metrics có chi phí thấp.
2. Chỉ bật event cần thiết theo câu hỏi điều tra.
3. Dùng threshold để bỏ qua event quá ngắn hoặc ít giá trị.
4. Giới hạn thời gian recording và dung lượng file.
5. Hạn chế stack trace ở event tần suất cao.
6. Dùng sampling khi mục tiêu là xác định xu hướng CPU hoặc allocation.
7. Tránh tạo heap dump trừ khi cần phân tích memory retention.
8. Đo throughput và latency trước/sau khi bật cấu hình.
9. Theo dõi dung lượng log và recording để tránh đầy đĩa.
10. Tắt recording hoặc event tạm thời sau khi kết thúc điều tra.

Đừng đồng nhất “overhead thấp” với “không ảnh hưởng”. Cấu hình tốt trên staging có thể tạo tải khác trên production do số thread, tần suất event, tốc độ request và heap size khác nhau.

## 12. Bảo vệ artifact sau khi thu thập

Ngay cả khi đã giảm dữ liệu nhạy cảm trong nguồn, file chẩn đoán vẫn cần được quản lý như một bản sao dữ liệu production.

| Kiểm soát | Cách áp dụng |
|---|---|
| Access control | Thư mục riêng, quyền đọc theo nhóm điều tra được phê duyệt |
| Encryption at rest | Mã hóa volume/object storage hoặc artifact theo chính sách |
| Encryption in transit | Truyền qua kênh TLS hoặc hệ thống chuyển file được quản lý |
| Retention | Đặt thời hạn ngắn phù hợp với mục đích điều tra |
| Integrity | Ghi nhận checksum/metadata để phát hiện artifact bị thay đổi |
| Audit | Ghi lại ai tạo, tải, đọc hoặc xóa artifact |
| Redaction | Lọc dữ liệu trước khi chia sẻ; không sửa file gốc nếu cần giữ bằng chứng điều tra |
| Disposal | Xóa theo quy trình lưu trữ và chính sách bảo mật |

Không đặt heap dump, JFR recording hoặc thread dump trong thư mục web server có thể tải công khai. Không gắn artifact vào ticket có phạm vi người đọc rộng hơn nhóm điều tra.

Khi cần chia sẻ với nhóm khác hoặc nhà cung cấp, chỉ chuyển bản đã được phê duyệt, giới hạn người nhận và dùng kênh trao đổi bảo mật.

## 13. Quy trình chẩn đoán production theo mức độ xâm lấn

Nên đi từ biện pháp ít xâm lấn đến biện pháp tạo artifact lớn:

1. **Metrics và health indicators:** kiểm tra CPU, heap usage, GC pause, thread count, request latency, error rate và queue depth.
2. **Log đã chuẩn hóa:** dùng correlation ID để tìm nhóm request lỗi mà không cần ghi payload.
3. **JFR default recording:** thu một khoảng thời gian có giới hạn để xem GC, execution sample, lock và event liên quan.
4. **Thread dump:** dùng khi cần hiểu thread đang chờ ở đâu hoặc có deadlock; với virtual thread, chọn lệnh dump phù hợp của JDK 21.
5. **JFR profile hoặc event chi tiết:** chỉ bật khi cần xác định call path, allocation hoặc lock contention sâu hơn.
6. **Heap dump:** chỉ tạo khi cần phân tích memory leak, object retention hoặc OutOfMemoryError và đã chuẩn bị dung lượng, quyền truy cập, retention.

Mỗi lần thu thập nên ghi lại incident ID, JVM PID, phiên bản JDK, thời gian bắt đầu/kết thúc, cấu hình JFR và người thực hiện. Không ghi secret vào metadata điều tra.

## 14. Kiểm tra trước khi bật chẩn đoán

Trước khi thu thập dữ liệu trên production, hãy xác nhận:

- Câu hỏi điều tra cụ thể là gì?
- Event hoặc artifact tối thiểu nào trả lời được câu hỏi đó?
- Có trường nào chứa PII, credential, payload hoặc thông tin nội bộ không?
- JFR dùng `default` hay `profile`; recording kéo dài bao lâu?
- Stack trace và custom event fields có thực sự cần thiết không?
- Heap dump hoặc thread dump có thể lớn đến mức nào?
- Thư mục lưu có đủ dung lượng, quyền truy cập và encryption phù hợp không?
- Ai được phép tải và phân tích file?
- Retention và quy trình xóa đã được xác định chưa?
- Có cách tắt recording hoặc thu thập sau khi điều tra không?
- Overhead đã được đánh giá trên workload đại diện chưa?

## 15. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Ghi toàn bộ request/response vào log | Lộ PII, token và dữ liệu nghiệp vụ | Chỉ ghi metadata allowlist |
| Đưa secret vào system property hoặc command line | Secret có thể xuất hiện trong process/runtime diagnostics | Dùng secret manager hoặc cơ chế lưu trữ được bảo vệ |
| Bật JFR profile liên tục mà không đo | Tăng event volume, file size và overhead | Dùng default cho recording dài hạn; profile có thời hạn |
| Ghi raw URL hoặc exception message vào JFR | Recording chứa dữ liệu nhạy cảm | Chuẩn hóa field và loại bỏ payload |
| Tạo heap dump thường xuyên | Pause, I/O lớn và nhiều bản sao dữ liệu nhạy cảm | Chỉ dump khi có mục tiêu điều tra cụ thể |
| Mở remote JMX không bảo vệ | Lộ runtime data hoặc cho phép thao tác trái phép | Authentication, TLS, firewall và least privilege |
| Lưu artifact trong thư mục chia sẻ rộng | Người không liên quan có thể đọc dữ liệu production | Thư mục riêng, audit và retention |
| Không rotation log/JFR | Đầy đĩa và gián đoạn dịch vụ | Giới hạn dung lượng, tuổi file và theo dõi storage |
| Bật mọi event/stack trace | Overhead và lượng dữ liệu vượt nhu cầu | Chọn event theo giả thuyết điều tra |

## Kết luận

Quan sát runtime an toàn trong Java 21 cần cân bằng khả năng tìm nguyên nhân sự cố với bảo vệ dữ liệu và chi phí thu thập. Hãy giảm dữ liệu nhạy cảm ngay từ nguồn, dùng JFR default cho recording dài hạn và profile có giới hạn, chỉ tạo heap dump khi cần, bảo vệ thread dump/GC log/JMX và kiểm soát quyền truy cập, retention, encryption.

JFR và các công cụ JDK giúp thu thập chẩn đoán hiệu quả, nhưng artifact vẫn có thể tiết lộ dữ liệu production. Một quy trình tốt luôn xác định mục tiêu, phạm vi, thời hạn, overhead, người được truy cập và cách xóa dữ liệu trước khi bắt đầu thu thập.

## Tài liệu tham khảo

- [Java SE 21 API — jdk.jfr](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/module-summary.html)
- [Java SE 21 — JFR Runtime Guide](https://docs.oracle.com/en/java/javase/21/jfapi/flight-recorder-runtime-guide.html)
- [Java SE 21 — jcmd](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [Java SE 21 — jfr tool](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html)
- [Java SE 21 — Unified JVM Logging](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [Java SE 21 — Monitoring and Management Using JMX Technology](https://docs.oracle.com/en/java/javase/21/management/monitoring-and-management-using-jmx-technology.html)
- [Java SE 21 — Troubleshooting Guide](https://docs.oracle.com/en/java/javase/21/troubleshoot/)
- [JEP 349 — JFR Event Streaming](https://openjdk.org/jeps/349)
- [JEP 328 — Flight Recorder](https://openjdk.org/jeps/328)
