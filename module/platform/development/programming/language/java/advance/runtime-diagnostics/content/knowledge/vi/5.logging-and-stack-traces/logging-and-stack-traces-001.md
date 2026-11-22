# 5.1 Phân biệt nhật ký ứng dụng với JVM Unified Logging

> **Java Advance – runtime-diagnostics** · **5. Nhật ký và stack trace**

## 1. Một process Java có thể phát ra nhiều loại nhật ký

Khi mở log của một Java service, bạn có thể bắt gặp:

- Dòng do **mã ứng dụng** ghi khi nhận request, gọi database, retry hoặc bắt exception.
- Dòng do **JVM/HotSpot** phát ra về GC, safepoint, class loading, hoạt động của runtime hoặc môi trường thực thi.
- **Stack trace** của một exception không được bắt, do cơ chế xử lý exception hoặc ứng dụng in ra.
- Dòng từ **container, web server, framework, thư viện native, agent và hệ điều hành**.

Những dòng này có thể cùng xuất hiện trong terminal, file hoặc hệ thống tập trung như Loki/ELK, nhưng **nguồn tạo, cơ chế bật/tắt, metadata và câu hỏi chẩn đoán của chúng khác nhau**. Một dòng nằm trong Docker logs không tự động trở thành “application log”; một dòng có từ “GC” trong ứng dụng không tự động là Unified Logging.

Hai hệ thống chính của bài này:

1. **Application logging**: ứng dụng/framework chủ động ghi các **sự kiện nghiệp vụ và hành vi trong mã Java** qua java.util.logging (JUL), SLF4J + Logback/Log4j2, System.Logger hoặc framework tương ứng.
2. **JVM Unified Logging (UL)**: hệ thống ghi log từ **các thành phần JVM**, chủ yếu được cấu hình bằng tùy chọn **-Xlog** của HotSpot, sử dụng *tag*, *level*, *decorator* và *output*.

Mục tiêu không phải chọn một trong hai. Khi chẩn đoán runtime, ta thường **cần cả hai**, mỗi loại trả lời một lớp câu hỏi khác nhau.

### Kết quả học tập

Sau bài này bạn có thể: nhận diện dòng log thuộc nguồn nào; chọn application log hay Unified Logging để kiểm tra một giả thuyết; đọc cú pháp -Xlog, tag/level/decorator/output; giải thích vì sao log nằm chung một file nhưng vẫn không cùng hệ thống; liên kết log ứng dụng, JVM, exception/stack trace và metric trên timeline; và bật logging chẩn đoán với phạm vi, thời lượng và chi phí có kiểm soát.

## 2. So sánh theo nguồn, mục đích và quyền điều khiển

| Tiêu chí | Nhật ký ứng dụng | JVM Unified Logging |
| --- | --- | --- |
| **Ai phát log?** | Application code, Java framework, thư viện qua logger của ứng dụng | JVM runtime/HotSpot và các thành phần VM có hỗ trợ Unified Logging |
| **Muốn trả lời gì?** | Request nào thất bại, bước nghiệp vụ nào lỗi, downstream trả lời gì, retry tại đâu? | GC nào xảy ra, JVM có safepoint nào, class được load/unload thế nào, VM đang làm gì? |
| **API/cấu hình** | Logger API, file cấu hình Logback/Log4j2/JUL, framework settings | Tùy chọn **-Xlog**, và một số cấu hình runtime qua **jcmd VM.log** |
| **Phân loại** | Logger name/category, level, MDC/structured fields theo framework | Tag set như *gc*, *safepoint*, *class+load* và mức *error, warning, info, debug, trace* |
| **Ngữ cảnh request** | Có thể ghi requestId, traceId, tenant, route, status nếu ứng dụng cung cấp | Không tự có requestId/traceId nghiệp vụ; thường có timestamp/uptime/PID/thread ID qua decorator |
| **Output** | Console, file, collector, appender/handler, JSON… tùy cấu hình | stdout, stderr, file và cơ chế xoay file của -Xlog |
| **Stack trace** | Có thể gắn Throwable để formatter/appender in exception stack | Một số log JVM có chi tiết VM; không thay thế stack trace của exception ứng dụng |
| **Đổi level** | Theo cấu hình/application management của framework | Qua -Xlog khi khởi động, hoặc VM.log với JVM đang chạy nếu được hỗ trợ và cho phép |
| **Rủi ro khi bật chi tiết** | Volume, dữ liệu nhạy cảm, overhead của formatter/appender | Volume sự kiện VM, CPU/I/O, disk, độ nhiễu; mức trace có thể rất lớn |

**Ranh giới quan trọng:** JVM Unified Logging **không phải** facade cho application logger. Đặt *-Xlog:gc=debug* không tự nâng logger *com.company.payment* lên DEBUG; đặt Logback root level DEBUG cũng không tự mở chi tiết GC của HotSpot. Bạn phải cấu hình đúng **bộ phát** cần quan sát.

Cũng cần phân biệt **framework logger** với *System.out.println*: câu lệnh println chỉ viết dữ liệu lên một luồng xuất, không tự mang severity, logger name, trace ID, format chuẩn hoặc rotation. Một framework có thể được cấu hình đẩy log ra cùng stdout, nhưng việc chung đích không làm hai cơ chế trở thành một.

## 3. Application logging: nhật ký theo dòng xử lý và nghiệp vụ

### 3.1 Nội dung phù hợp

Một ứng dụng xử lý checkout có thể ghi:

- Request bắt đầu: route template, request ID, trace ID, mã phiên bản.
- Thời gian gọi dependency, kết quả thành công/thất bại, retry count.
- Exception liên quan nghiệp vụ, loại lỗi, thao tác hiện tại và outcome.
- Thời gian xử lý hoặc trạng thái hoàn tất để đối chiếu với metric p95/p99.
- Sự kiện vận hành quan trọng: chuyển trạng thái circuit breaker, thay đổi cấu hình được phê duyệt, retry policy.

Một ứng dụng **không nên** ghi thông tin cá nhân, token, password, toàn bộ payload thanh toán hay SQL parameters nhạy cảm chỉ để debug. Có requestId ngẫu nhiên/đã kiểm soát giúp truy vết; không có nghĩa cần log toàn bộ dữ liệu của request.

Ví dụ một bản ghi ứng dụng giả định:

~~~text
2026-10-29T08:10:12.340Z INFO service=checkout route=/orders/{id} traceId=t-9 requestId=r-42 message="start"
2026-10-29T08:10:13.105Z ERROR service=checkout traceId=t-9 requestId=r-42 exception=TimeoutException message="payment call timed out"
~~~

Đây là **log minh họa**, không phải định dạng bắt buộc của JUL, Logback hay Log4j2. Timestamp, field, mức lỗi, JSON hoặc text do cấu hình và code quyết định. Trong ứng dụng thực, không biến ID người dùng hay URL có định danh động thành metric label có cardinality lớn; log/trace có thể chứa correlation ID theo chính sách bảo mật.

### 3.2 Logger name, level, handler/appender

Một mô hình phổ biến:

~~~text
Application code
  -> Logger ("com.example.checkout")
  -> Level/filter (INFO/WARN/ERROR...)
  -> Formatter/encoder (text hoặc JSON)
  -> Handler/appender (stdout, stderr, file, collector...)
  -> Log pipeline / storage
~~~

- **Logger/category** thường phản ánh class/package hoặc thành phần nghiệp vụ.
- **Level** giúp lọc độ chi tiết. Tên mức level khác nhau theo framework: JUL dùng *SEVERE/WARNING/INFO/FINE/...*, Logback/Log4j2 thường dùng *ERROR/WARN/INFO/DEBUG/TRACE*. Chúng **không phải** trực tiếp là các mức của -Xlog.
- **Context** (MDC hoặc structured arguments) là cơ chế của logger/framework ứng dụng, không phải một decorator tự động của HotSpot.
- **Handler/appender** có quyền quyết định gửi sang stdout hay stderr hoặc file. JUL ConsoleHandler mặc định thường hướng đến stderr; cấu hình framework khác có thể dùng stdout. **Không suy ra nguồn log chỉ qua luồng xuất**.

Nếu một handler có async queue hoặc remote shipper, log có thể trễ, bị drop khi quá tải hoặc xuất không đúng thứ tự toàn cục. Mất một dòng log không tự chứng minh sự kiện không xảy ra.

### 3.3 Những giới hạn của application logs

Ứng dụng chỉ biết những gì được instrument hoặc framework ghi. Nếu mã không log GC pauses hoặc class unloading, application logs không thể tự cung cấp bằng chứng về chúng. Ngược lại, VM có thể biết GC đang diễn ra nhưng không biết requestId nào đang chờ thanh toán trừ khi có cơ chế liên kết quan sát khác.

Khi request báo timeout, cần app log về network/dependency/exception và có thể cần VM log về GC/safepoint để phân biệt thời gian chờ do dịch vụ ngoài với thời gian ngừng ứng dụng ở tầng runtime.

## 4. JVM Unified Logging: nhật ký phát ra từ JVM

Unified Logging là cơ chế chuẩn hóa logging của HotSpot (nền tảng từ JDK 9, có mặt trên JDK 17+). Nó dùng **tag set** để chỉ bộ phận VM và **level** để chọn mức chi tiết.

Những nhóm thông tin thường hữu ích khi chẩn đoán:

| Tập tag / selector | Điều tra gì? | Lưu ý |
| --- | --- | --- |
| *gc* | Thông điệp GC chính | Không tự bao gồm mọi bản ghi có kết hợp tag GC khác |
| *gc*=info* | Các tag set có chứa *gc*, ở mức info trở lên theo nghĩa ngưỡng verbosity | Wildcard mở rộng phạm vi, log có thể tăng mạnh |
| *gc+heap=debug* | Các thông điệp gắn chính xác tập tag *gc,heap* ở mức debug | Không tương đương chọn *gc* hoặc *heap* riêng |
| *safepoint* | Sự kiện safepoint của VM | Tính có mặt và cách ghi cụ thể phụ thuộc JDK/VM |
| *class+load* | Class loading | Có thể phát sinh rất nhiều dòng, nhất là startup |
| *os+container* | Thông tin runtime về container khi được hỗ trợ | Tag/sự kiện cụ thể phải kiểm tra trên JVM đang dùng |

**Các selector là ví dụ HotSpot/JDK thông dụng, không phải cam kết mỗi JVM/vendor/version đều phát đúng các sự kiện như nhau.** Luôn xem *java -Xlog:help* của phiên bản thực tế.

### 4.1 Tag set và dấu cộng khác với dấu phẩy

Trong cú pháp -Xlog:

- Dấu **+** ghép các tag thuộc **một tag set**, ví dụ *gc+heap*.
- Dấu **,** giữa các selection định nghĩa **nhiều lựa chọn**, ví dụ *gc,safepoint*.
- Dấu **\*** ngay sau tag set tạo **wildcard match**: *gc\** khớp các tập tag có chứa *gc*; không có wildcard thường yêu cầu **khớp chính xác tag set**.

Ví dụ:

~~~bash
java -Xlog:gc=info MyApp
java -Xlog:gc*=info MyApp
java -Xlog:gc+heap=debug MyApp
java -Xlog:gc,safepoint MyApp
~~~

Trong bảng so sánh trên, hai selector đầu **không đồng nhất**: *gc=info* chỉ chọn các thông điệp có tập tag đúng *gc*, còn *gc*=info* (dấu * nằm ở cuối selector) mở rộng sang nhiều tag set chứa *gc* như *gc,heap*, *gc,start*, tùy JVM. Vì vậy hai dashboard “có GC logs” vẫn có độ chi tiết khác nhau. Những lựa chọn có dấu **+** và **,** cũng không hoán đổi được.

**Cảnh báo về shell:** một số ký tự đặc biệt trong argument cần quote tùy shell. Các command ở trên chỉ minh họa cú pháp JVM; khi đặt trong Dockerfile, YAML hoặc shell script, xác minh escaping và nguyên vẹn của argument sau khi triển khai.

### 4.2 Levels của Unified Logging

Các mức hỗ trợ thông dụng:

~~~text
off  error  warning  info  debug  trace
~~~

Nói theo độ chi tiết, *trace* thường tạo nhiều thông tin hơn *debug*, còn *info* thiên về các sự kiện thông thường. Tên mức level của VM **không nhất thiết mapping một-một** với logger framework ứng dụng.

Điểm ít người để ý: **mặc định không phải “JVM không log gì”**. Nếu không cấu hình -Xlog, HotSpot có mặc định tương đương việc ghi các thông báo **warning/error** với các tag, thường ra stdout và decorator *uptime,level,tags*. Bật selector *-Xlog:gc* sẽ mở thêm thông tin GC mức info, nhưng không cần tắt logging mặc định.

**Không dùng -Xlog:disable một cách tùy tiện.** Chỉ thị này tắt mọi output của hệ Unified Logging, bao gồm cả mặc định warning/error, cho đến khi cấu hình khác được bật lại. Việc thiếu warning sau đó có thể làm mất bằng chứng chẩn đoán.

### 4.3 Vì sao JVM log không chứa requestId?

JVM biết thread, heap, class, GC cycle, safepoint và nhiều sự kiện nội bộ. Nó không mặc định biết *requestId* được đặt trong MDC của ứng dụng. Một dòng GC có thể chứa **GC ID**, **uptime** và **PID**, nhưng GC ID không phải request ID và thread ID trong decorator không tự bằng business correlation ID.

Liên kết thường làm bằng **timestamp + host/container/pod + PID/JVM instance + trace/metric**. Nếu hai JVM cùng in ra stdout của collector mà thiếu thông tin instance, rất dễ quy GC pause của JVM A cho request lỗi trên JVM B.

## 5. Cú pháp -Xlog: đọc từ trái sang phải

Dạng tổng quát (theo tài liệu lệnh java cho HotSpot):

~~~text
-Xlog:[what]:[output]:[decorators]:[output-options]
~~~

Trong đó các phần sau -Xlog có thể được bỏ qua để dùng mặc định. Một ví dụ đầy đủ:

~~~bash
java -Xlog:gc*=debug:file=gc-%p.log:time,uptime,level,tags:filecount=5,filesize=10M MyApp
~~~

Phân tích:

| Phần | Giá trị ví dụ | Ý nghĩa |
| --- | --- | --- |
| *what* | *gc*=debug* | Chọn tag set có *gc* (wildcard) với mức từ debug và các mức ít chi tiết hơn |
| *output* | *file=gc-%p.log* | Ghi ra file; *%p* được mở rộng thành PID |
| *decorators* | *time,uptime,level,tags* | Thêm thời gian lịch, thời gian từ lúc VM chạy, severity và tag set |
| *output-options* | *filecount=5,filesize=10M* | Cấu hình xoay log tối đa theo số file/kích thước đích gần đúng |

Cú pháp trên thuộc **JVM launch flags**, phải đặt **trước main class hoặc -jar**:

~~~bash
java -Xlog:gc=info -jar service.jar
~~~

Nếu đặt *-Xlog:gc=info* sau *-jar service.jar*, nó thường trở thành **application argument**, không phải JVM option; chương trình có thể nhận chuỗi nhưng JVM không đổi cấu hình logging.

### 5.1 Các output của Unified Logging

- **stdout**: ví dụ *-Xlog:gc:stdout*; thích hợp nếu pipeline container chủ động thu stdout.
- **stderr**: ví dụ *-Xlog:gc:stderr*; có thể giúp tách luồng, nhưng collector có thể hợp nhất lại.
- **file=...**: ví dụ *-Xlog:gc:file=gc.log*; cần kiểm tra quyền ghi, vị trí trong container, dung lượng, rotation, cơ chế thu và retention.

Các lựa chọn output không nói gì về application logger. Bạn có thể cấu hình app logger ra stdout và JVM UL ra một file riêng, hoặc cả hai ra stdout. **Cùng đích không có nghĩa cùng bộ lọc hay cùng cấu trúc**.

Ví dụ file riêng cho GC:

~~~bash
java -Xlog:gc*:file=gc-%p.log:time,uptime,level,tags:filecount=3,filesize=5M -jar service.jar
~~~

Nếu file thuộc filesystem tạm của container và không có volume/shipper, nó có thể biến mất khi pod bị thay. Nếu sử dụng file rotation, xác minh cách collector theo dõi file đổi tên và không đọc lại hoặc bỏ sót các phân đoạn.

**Không giả định filecount/filesize là retention vĩnh viễn.** File size rotation là cơ chế cục bộ, còn retention tập trung, lưu trữ, bảo vệ dữ liệu và lifecycle pod phải được thiết kế riêng.

### 5.2 Decorator: timestamp của VM không phải timestamp của app

Các decorator thông dụng:

- *time*: thời gian lịch theo định dạng thời gian có timezone.
- *utctime*: mốc UTC.
- *uptime*: thời gian kể từ khi JVM khởi động, ví dụ 12.345s.
- *level*: severity của thông điệp VM.
- *tags*: bộ tag phát message.
- *pid*: process ID.
- *tid*: thread identifier do hệ JVM log ghi.
- *hostname*: tên host.

Nếu không chỉ định decorators, mặc định thông dụng là **uptime,level,tags**. Vì vậy mẫu kiểu:

~~~text
[3.452s][info][gc] GC(0) Pause Young (Normal) ... 12M->4M(128M) 3.4ms
~~~

là **minh họa định dạng**, không phải stdout chắc chắn trên mọi JDK/GC. Có dấu *[3.452s]* không có nghĩa sự kiện xảy ra lúc 03:45:02 theo giờ hệ thống; nó thường là **uptime của JVM**. Muốn ghép với thời điểm request thất bại trong app log, cần biết JVM start time hoặc bật decorator *time/utctime*.

Ví dụ với decorator lịch và uptime:

~~~bash
java -Xlog:gc=info:stdout:time,uptime,level,tags,pid -jar service.jar
~~~

Điều này tạo metadata hữu ích để đối chiếu, nhưng không làm log ứng dụng tự động có cùng timestamp format. Hệ log thu thập tập trung còn có thể gắn **ingestion timestamp** khác với **event timestamp**; đừng coi chúng hoán đổi được khi cần xác định thứ tự nhân quả.

### 5.3 Thử hỗ trợ và tag thực tế

Kiểm tra lệnh java của JVM sẽ chạy:

~~~bash
java -version
java -Xlog:help
~~~

*-Xlog:help* hiển thị cú pháp, tags, levels, decorators, ví dụ được hỗ trợ trên build đó. Đây là nguồn tốt hơn việc chép nguyên cờ từ một JDK/vendor khác và mặc định nó luôn hoạt động.

Không cần bật **all=trace** trên production chỉ để khám phá tag. *Trace* có thể tạo volume và overhead lớn. Bắt đầu từ phạm vi hẹp, ít chi tiết, rồi tăng lên khi có giả thuyết và thời hạn cụ thể.

## 6. Hai luồng log có thể cùng vào stdout của một container

Ví dụ topology:

~~~text
[Application code]
    |
    +-- SLF4J/Logback/JUL -> stdout ------------+
                                                |
[JVM/HotSpot]                                  +-- container runtime
    |                                           |        |
    +-- -Xlog:gc*=info:stdout ------------------+        +-- shipper/collector
                                                         |
                                                         +-- dashboard/query
~~~

Người vận hành nhìn thấy nhiều dòng trong cùng lệnh *docker logs*, *kubectl logs* hoặc trong một index tập trung. Nhưng phép lọc của application logger vẫn điều khiển **log ứng dụng**, còn -Xlog vẫn điều khiển **log JVM**.

**Ví dụ dòng từ hai nguồn trong một luồng (minh họa):**

~~~text
2026-10-29T08:21:04.100Z INFO service=checkout requestId=r-7 message="handling request"
[2026-10-29T08:21:04.130+0000][9.451s][info][gc] GC(17) Pause Young ... 5.2ms
2026-10-29T08:21:04.180Z WARN service=checkout requestId=r-7 message="downstream slow"
~~~

Dòng giữa có decorator/tag theo Unified Logging. Hai dòng ngoài có cấu trúc do application logger quy định. Việc chúng xuất gần nhau theo thời gian **không tự chứng minh GC gây ra downstream slow**: GC pause có thể chỉ 5.2 ms trong khi request chậm hàng trăm ms. Phải kiểm tra mức chồng lấp thời gian, cùng instance, tổng pause, request trace, CPU và dependency latency.

Khi collector hợp nhất stdout và stderr, thứ tự nhận được có thể khác thứ tự sự kiện thực, đặc biệt giữa các thread/async queue. Với một incident, cần phân biệt timestamp do **nguồn phát**, **runtime** và **collector** gắn.

## 7. Ví dụ Java 17+ độc lập: log ứng dụng không thuộc -Xlog

Chương trình dưới dùng **java.util.logging (JUL)** chuẩn JDK, không dùng framework ngoài. Để stdout cố định và dễ so sánh, nó tự khai báo một **Handler** với format xác định, thay vì phụ thuộc timestamp/formatter mặc định. Ví dụ cố tình tạo và bắt một exception, gắn nó vào LogRecord. Handler minh họa chỉ in **loại** exception, không in toàn bộ stack trace; trong production cần formatter/appender phù hợp mục tiêu điều tra.

Tạo file **AppVsVmLoggingDemo.java**:

~~~java
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class AppVsVmLoggingDemo {
    private static final Logger LOG = Logger.getLogger("demo.checkout");

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);
        Handler stdout = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (!isLoggable(record)) return;
                String cause = record.getThrown() == null ? ""
                    : " cause=" + record.getThrown().getClass().getSimpleName();
                System.out.println(record.getLevel().getName()
                    + " [" + record.getLoggerName() + "] "
                    + record.getMessage() + cause);
            }

            @Override public void flush() { System.out.flush(); }
            @Override public void close() { }
        };
        stdout.setLevel(Level.ALL);
        LOG.addHandler(stdout);
        try {
            LOG.info("requestId=demo-001 checkout-start");
            try {
                throw new IllegalStateException("simulated");
            } catch (IllegalStateException ex) {
                LOG.log(Level.SEVERE, "requestId=demo-001 checkout-failed", ex);
            } finally {
                LOG.info("requestId=demo-001 checkout-end");
            }
        } finally {
            stdout.flush();
            LOG.removeHandler(stdout);
        }
    }
}
~~~

Biên dịch/chạy trên JDK 17 trở lên:

~~~bash
javac AppVsVmLoggingDemo.java
java AppVsVmLoggingDemo
~~~

**Ba dòng do Handler ứng dụng phát ra, chính xác:**

~~~text
INFO [demo.checkout] requestId=demo-001 checkout-start
SEVERE [demo.checkout] requestId=demo-001 checkout-failed cause=IllegalStateException
INFO [demo.checkout] requestId=demo-001 checkout-end
~~~

Chương trình không dùng JVM -Xlog để phát ba dòng này. *LOG.log(Level.SEVERE, ... , ex)* gắn Throwable vào record; custom Handler chỉ tóm tắt loại Throwable. Với handler/formatter khác, có thể in cả stack trace nhiều dòng. Vì lỗi đã được bắt nên JVM không buộc phải tự in exception trên stderr.

Thử bật một nguồn VM log **riêng** trong cùng tiến trình:

~~~bash
java -Xlog:class+load=info:stdout:uptime,level,tags AppVsVmLoggingDemo
~~~

Khi chạy, JVM có thể in **rất nhiều** sự kiện class loading kèm *[info][class,load]*, bên cạnh ba dòng ứng dụng. Thứ tự và số dòng JVM phụ thuộc build, classpath, quá trình tải lớp và môi trường; **không có stdout cố định cho toàn tiến trình** khi bật thêm -Xlog.

Nếu muốn quan sát tách biệt:

~~~bash
java -Xlog:class+load=info:file=classload-%p.log:uptime,level,tags AppVsVmLoggingDemo
~~~

Ba dòng ứng dụng vẫn được Handler gửi ra stdout; sự kiện class loading được Unified Logging gửi tới file theo PID. Không thay đổi một dòng Java application logging nào. **Không nên bật class-load logging chi tiết thường xuyên ở production nếu không có lý do và kế hoạch thu dữ liệu.**

### 7.1 Vì sao demo không là chuẩn production?

Để dễ học, custom Handler dùng *System.out.println* đồng bộ, không có escaping, structured JSON, dữ liệu bí mật handling, backpressure hay stack trace đầy đủ. Nó cũng chỉ mô phỏng một request. Trong production hãy dùng framework/handler đã được chuẩn hóa, thêm trường ngữ cảnh cần thiết, hỗ trợ multi-thread, rotation/collector và policy lưu trữ. Demo chỉ chứng minh **sự độc lập giữa producer ứng dụng và producer JVM**.

## 8. Stack trace ở đâu trong hai hệ logging?

**Stack trace** là tập các stack frame mô tả đường gọi tại thời điểm Throwable/điểm lấy mẫu, không phải một “loại logger” riêng. Nó có thể được:

1. Ghi qua application logger khi code truyền *Throwable* vào LogRecord/SLF4J/Log4j2.
2. In trực tiếp bằng *Throwable.printStackTrace()* hoặc bởi cơ chế báo uncaught exception (thường tới stderr).
3. Thu từ thread dump/JFR/profiler hoặc công cụ chẩn đoán khác, trong đó stack là dữ liệu trạng thái/thực thi chứ không nhất thiết là event log của framework.
4. Xuất dưới dạng chi tiết của một số sự kiện VM, tùy tag/command và JVM.

**Cần phân biệt ba câu thường bị nói lẫn:**

- “Ứng dụng log ERROR có exception stack”: ứng dụng/framework đã ghi Throwable và formatter có thể in stack.
- “Terminal có stack trace”: có thể là uncaught exception trên stderr; chưa chắc đi qua logger của ứng dụng.
- “JVM Unified Logging bật”: không có nghĩa mọi exception nghiệp vụ đều được in đầy đủ stack frame.

Ví dụ mô tả một Throwable do framework ghi (minh họa):

~~~text
ERROR checkout requestId=r-9 Payment failed
java.lang.IllegalStateException: payment rejected
    at com.example.CheckoutService.pay(CheckoutService.java:42)
    at com.example.CheckoutHandler.handle(CheckoutHandler.java:18)
~~~

Tại sao stack này có giá trị? Nó chỉ ra đường gọi **tại điểm ném/ghi exception** trong ngữ cảnh ứng dụng. Nhưng nó có thể không nói gì về:

- GC pause nào diễn ra cùng lúc.
- Thread khác đang giữ lock gì.
- Khi nào class được load hay safepoint xảy ra.
- Timeout do dependency, DNS hoặc queue wait như thế nào nếu stack chỉ phản ánh điểm báo lỗi.

Vì thế khi cần bằng chứng runtime, ta bổ sung Unified Logging/metrics/JFR/thread dump theo giả thuyết, không kỳ vọng stack trace ứng dụng giải thích mọi vấn đề.

### 8.1 Multi-line stack trace và hệ log tập trung

Một exception stack có thể trải nhiều dòng. Nếu shipper coi **mỗi dòng** là một event riêng, những frame “at ...” có thể mất requestId và bị lẫn với stack khác. Dùng định dạng exception field trong JSON hoặc multiline parsing theo pipeline có kiểm soát. Không tự cắt stack ở vài dòng đầu rồi kết luận không có *Caused by* hoặc *Suppressed* nếu hệ thống có thể đã truncate vì giới hạn kích thước.

Khi chia sẻ log cho đội khác, lọc argument nhạy cảm, đường dẫn nội bộ, username hoặc token. Stack trace hữu ích cho chẩn đoán nhưng cũng có thể tiết lộ cấu trúc hệ thống.

## 9. Kết hợp application logs và Unified Logging để phân biệt nguyên nhân

Đặt tình huống: p99 của endpoint /checkout tăng từ 180 ms lên 1,2 s sau deploy. Một vài request timeout. Nếu chỉ xem application logs, bạn thấy *TimeoutException*; nếu chỉ xem JVM GC logs, bạn thấy các lần Young GC. Chưa đủ cơ sở kết luận Young GC gây timeout.

Quy trình có bằng chứng:

1. **Định nghĩa triệu chứng:** route, status, time range, instance/pod, request count, timeout rate, latency distribution.
2. **Xem application log:** request/trace ID, thời điểm nhận request, gọi DB/payment, retry, exception, thông điệp failure. Phải chắc timestamp thuộc cùng timezone/cùng clock basis.
3. **Xem JVM log:** các sự kiện GC/safepoint và duration trên **cùng JVM instance** trong cửa sổ; chú ý *uptime* khác wall-clock.
4. **Đối chiếu metrics:** CPU, heap, GC pause histogram, thread pool active/pending, completed request rate, error count.
5. **So timeline:** GC pause có trùng khoảng request bị chậm không? Tổng pause đủ lớn để giải thích 1,2 s không, hay chỉ 3–10 ms? Có dấu hiệu downstream wait?
6. **Lập giả thuyết cạnh tranh:** H1 do GC pause; H2 dependency latency; H3 thread pool/connection pool saturation; H4 retry amplification.
7. **Kiểm chứng:** dùng trace span, thread dump/JFR hoặc log theo tag liên quan với giới hạn chi phí; so trước/sau cùng tải; ghi mức tin cậy.

### Tình huống A – JVM chịu allocation pressure

**Ứng dụng:** request chậm rải rác; app log có requestId/time, không có lỗi code rõ rệt. **VM:** GC event frequency tăng, tổng GC pause time tăng trùng với latency spike, heap allocation rate cũng tăng. Đây là **bằng chứng ủng hộ** giả thuyết allocation/GC pressure, không phải chứng minh duy nhất; cần đối chiếu đúng GC duration và request timeline, CPU, heap và workload.

### Tình huống B – Dependency timeout nhưng GC bình thường

**Ứng dụng:** nhiều TimeoutException cùng dependency, retry count tăng, trace cho thấy chờ HTTP/downstream. **VM:** chỉ có những lần GC ngắn, không trùng với khoảng 1–2 s request chậm. Hướng điều tra ưu tiên network, retry policy, connection pool, downstream và queue, thay vì bật *gc=trace* vô thời hạn.

### Tình huống C – JVM safepoint hoặc class loading ảnh hưởng startup

**Ứng dụng:** startup delay, warmup chậm hoặc request đầu tiên cao latency. **VM:** class loading/compilation hoặc safepoint events tăng gần thời điểm khởi động. Đối chiếu deployment startup, JIT warmup, readiness gating, class loading và GC bằng các tag thích hợp; không cho rằng mọi dòng *class+load* là sự cố.

### Tình huống D – Exception ứng dụng nhưng không thấy GC log

**Ứng dụng:** stack trace rõ đường gọi dẫn tới IllegalArgumentException. **VM:** không có GC info tương ứng vì không xảy ra GC, hoặc chưa bật selector phù hợp, hoặc log đổ tới file khác. Không được nói “JVM không phát lỗi nên app không lỗi”; GC log không có nghĩa vụ ghi exception nghiệp vụ.

## 10. Cách chọn nguồn log theo giả thuyết

| Câu hỏi điều tra | Ưu tiên | Bằng chứng bổ sung |
| --- | --- | --- |
| Đơn hàng rớt tại bước nào? | Application log, trace, exception stack | Dependency status, retry metric |
| Tại sao request có 2 lần gọi payment? | Application log theo requestId/traceId | Attempt count, trace graph |
| Có GC pause trùng p99 spike? | JVM Unified Logging tag gc và GC metrics | JFR, request timeline |
| JVM load/unload class bất thường? | Unified Logging tag class+load/unload nếu cần | Metaspace metrics, classloader stats |
| Thread pool hết worker? | Application framework metrics/log, thread dump | JVM safepoint, CPU, queue |
| App in ERROR nhưng không có stack? | Formatter/appender cấu hình, cách gọi logger | Có truyền Throwable không, collector có truncate không |
| Không thấy log dù JVM đã restart? | Kiểm tra container stdout/stderr, output file, rotation, collector | Process start time, app shutdown logs |
| Cần biết lỗi cấu hình từ JVM startup? | JVM startup warnings/flags, VM logging | Java command-line, deployment config |
| Một pod khác hoạt động bình thường? | So app + JVM logs theo instance/version | Traffic mix và resource limits |

**Nguồn nào không trả lời được câu hỏi nào?** Không tìm requestId trong GC tags; không kỳ vọng WARN của application logger sẽ xuất hiện chỉ vì bật *-Xlog:all=warning*; không dùng UncaughtExceptionHandler như thay thế log toàn bộ request; không dùng một dòng stack trace để kết luận memory leak hoặc deadlock.

## 11. Thay đổi JVM logging ở runtime bằng jcmd VM.log

Một số JVM HotSpot cho phép xem/chỉnh cấu hình Unified Logging của **JVM đang chạy** thông qua diagnostic command *VM.log*.

Ví dụ sử dụng **PID giả định 12345**, thay bằng PID JVM đích được xác nhận:

~~~bash
jcmd 12345 VM.version
jcmd 12345 VM.log list
jcmd 12345 help VM.log
~~~

Nếu *VM.log list* được hỗ trợ, nó cho thấy cấu hình logging hiện hành của VM. Lệnh *help VM.log* cho biết đối số như *what*, *output*, *decorators*, *output_options*, *list* và *rotate* theo build hiện tại.

**Thay đổi runtime không đồng nghĩa cập nhật vĩnh viễn launch configuration.** Nếu JVM restart, cấu hình startup/deployment vẫn quyết định state ban đầu. Trước khi bật thêm tags hoặc đổi output trên production, cần có quyền vận hành, mục tiêu, thời hạn, mức chi tiết và kế hoạch hoàn nguyên.

Ví dụ cách thể hiện đối số của lệnh (chỉ làm trên môi trường được phép và sau khi đọc help của JVM đích):

~~~bash
jcmd 12345 VM.log output=stdout what="gc*=debug"
~~~

Thao tác này **thay đổi cấu hình ghi log runtime**, không phải lệnh đọc thuần. Cú pháp và tên output có thể khác theo JDK; cần xác minh qua *VM.log list* trước/sau. Không bật *all=trace*, không xóa output hiện có hoặc dùng *disable* khi chưa hiểu ảnh hưởng. Với JVM không cho attach hoặc không hỗ trợ VM.log, cần dùng cấu hình launch/telemetry thay vì cố sửa quyền.

Cấu hình **application logging** động (nếu framework có API/JMX/actuator) là cơ chế **riêng**; không thể dùng *VM.log* để hạ logger package com.example từ DEBUG về INFO.

## 12. Log rotation, volume, overhead và chất lượng bằng chứng

Nhật ký càng chi tiết càng có giá: CPU cho formatting, I/O, disk, network, chi phí lưu trữ và áp lực đối với collector. Trong sự cố có traffic lớn, logging mức trace thiếu kiểm soát đôi khi làm tình hình tệ hơn.

### 12.1 Phân biệt các dạng rotation và backpressure

- Application logger dùng appender/handler và retention theo cấu hình riêng.
- Unified Logging file output có tùy chọn rotation như *filesize* và *filecount*; giá trị là mục tiêu gần đúng, không phải độ chính xác byte tuyệt đối.
- Container runtime có thể có log rotation độc lập; collector có thể áp chính sách retention khác.
- Khi -Xlog dùng chế độ bất đồng bộ *-Xlog:async* (nếu JVM hỗ trợ), bản ghi đưa vào buffer có thể bị **bỏ** khi buffer hữu hạn đầy; “không thấy một event” không tự là “không xảy ra”.
- Application async appender cũng có thể drop/suspend theo policy. Hỏi rõ độ tin cậy và chỉ số dropped log của pipeline khi phân tích những sự cố cực ngắn.

Với production, bắt đầu ở mức cần thiết, ưu tiên tag giới hạn và khoảng quan sát hữu hạn. Nếu cần theo dõi số lần/độ trễ liên tục với chi phí thấp, **metrics** thường phù hợp hơn ghi từng sự kiện ở mức debug. Dùng **traces** cho đường đi của request, **logs** cho chi tiết sự kiện, **JFR** cho profile sự kiện runtime có cấu trúc; chúng bổ sung nhau.

### 12.2 Vì sao timestamp dễ gây kết luận sai?

Một JVM log có decorator **uptime** và application log có timestamp UTC. Để ghép hai dòng cần biết JVM start time. Nếu JVM vừa restart, uptime bắt đầu lại từ gần 0. Collector timestamp có thể trễ vài giây so với event time vì buffering. Đồng hồ các máy có thể lệch nhau nếu time sync không ổn. Nếu kết luận “GC xảy ra đúng trước request failed 5 ms”, phải so đúng **event timestamp** và cùng **instance**.

Không nên dựa vào thứ tự các dòng từ nhiều stream để suy ra nhân quả. Dòng application WARN sau GC trong cùng terminal chỉ là **tương quan thời gian**, không phải bằng chứng GC gây WARN.

### 12.3 Bảo mật và sự riêng tư

- Application log: hạn chế PII, session key, payload request/response, access token và thông tin xác thực.
- JVM log: có thể lộ class names, paths, memory sizes, cấu hình runtime; command line hoặc heap dump đặc biệt nhạy cảm.
- Stack trace: có thể lộ thư mục, package structure, SQL, input hoặc chi tiết exception.
- Dùng least privilege, retention và redaction; không đăng toàn bộ log production công khai để debug.
- Log không nên tự biến thành công cụ giám sát người dùng ngoài phạm vi đã cho phép.

## 13. Lỗi phổ biến khi đọc hai loại log

| Hiểu sai | Điều đúng | Cách xử lý |
| --- | --- | --- |
| “Bật Logback DEBUG thì thấy GC detail” | Logback lọc sự kiện app; GC thuộc JVM UL | Bật tag -Xlog phù hợp |
| “Bật -Xlog:gc thì app INFO sẽ xuất hiện” | -Xlog không điều khiển application logger | Kiểm tra logger/handler/appender của app |
| “Tất cả dòng stdout là application log” | UL cũng có thể ghi stdout | Phân biệt producer/tag/formatter và nguồn instance |
| “Dòng [info][gc] là INFO của SLF4J” | Đó là level/tag trong JVM UL | Không map trực tiếp level giữa hai hệ |
| “gc+heap là gc hoặc heap” | Dấu + kết hợp tag trong một tag set | Phân biệt với dấu phẩy và wildcard |
| “gc=info giống gc*=info” | Không wildcard: exact tag-set; wildcard: tập có chứa tag | Kiểm tra selector theo JDK |
| “Không thấy GC log nên không có GC” | Có thể không bật tag, ghi file khác, collector mất data | Kiểm tra -Xlog config, output, metrics |
| “GC log có PID là request ID” | PID chỉ process; GC ID cũng không phải trace ID | Ghép bằng instance + timestamp + trace/metric |
| “Exception stack trace là JVM UL” | Có thể do app logger/printStackTrace/uncaught handler | Tìm nguồn phát và formatter |
| “VM.log có thể đổi logger com.example” | VM.log chỉ quản lý Unified Logging | Dùng cơ chế app logging riêng |
| “-Xlog:disable chỉ tắt debug” | Có thể tắt cả warning/error mặc định | Tránh trên production thiếu kiểm soát |
| “Một dòng GC trước lỗi chứng minh GC gây lỗi” | Tương quan chưa phải nguyên nhân | Đối chiếu pause duration, trace, metrics |
| “File GC xoay tức là đã có retention tập trung” | Rotation và retention là hai cơ chế | Kiểm tra file shipping và lifecycle |
| “Stack không có Caused by nên không có nguyên nhân sâu” | Collector có thể cắt/multiline parse sai | Kiểm tra raw log/formatter/truncation |

## 14. Quy trình chẩn đoán khi không thấy log mong đợi

**A. Không thấy application log:**

1. Xác nhận đúng service/version/instance, request thực sự đi vào đây.
2. Xác nhận logger name, level, appender/handler, filter, async queue.
3. Kiểm tra output thực: stdout/stderr/file; container collector có thu đích đó không?
4. Kiểm tra sampling, rate limiting, structured parsing, multiline/truncation.
5. Nếu error bị catch rồi nuốt không ghi gì, JVM Unified Logging cũng không tự giúp tạo application event đó.

**B. Không thấy JVM Unified Logging:**

1. Dùng *java -Xlog:help* của JDK phù hợp để kiểm tra selector/tag.
2. Xác nhận launch args thực tế trước main class hoặc -jar, và đang xem đúng JVM instance.
3. Kiểm tra output mặc định/file/stderr, quyền ghi, container mount và collector.
4. Xác nhận **event thực sự xảy ra**; bật *gc* không bắt buộc có GC trong một chương trình ngắn.
5. Nếu có quyền, xem *jcmd PID VM.log list* để biết cấu hình hiện tại; đừng tự thay đổi log level production mà không được phép.
6. Đối chiếu metrics/JFR để biết sự kiện không xảy ra hay chỉ không được ghi nhận/thu thập.

**C. Có application ERROR nhưng không có stack:**

1. Có truyền *Throwable* vào log API không? Chỉ ghi *ex.getMessage()* thường mất stack.
2. Formatter/encoder có cấu hình in stack hoặc exception JSON field không?
3. Collector có tách một stack trace thành nhiều event hoặc cắt bớt vì size limit không?
4. Có policy che bớt thông tin nhạy cảm khiến field bị loại không?

**D. Có log từ nhiều JVM xen kẽ:**

1. Xác định container/pod/host/PID/version cho từng dòng.
2. Đặt timestamp về cùng thời gian UTC, ghi rõ uptime và epoch thời điểm JVM start.
3. Phân nhóm log theo instance trước khi suy luận runtime.
4. Chỉ gộp khi mục tiêu là thống kê toàn dịch vụ, không dùng log VM của instance A làm nguyên nhân của request trên B.

## 15. Bài tập đọc log có đáp án

### Bài 1 – Nhận diện producer

Cho ba dòng minh họa:

~~~text
INFO [order.service] requestId=r-12 save-order
[4.100s][info][gc] GC(1) Pause Young ... 2.1ms
java.lang.IllegalArgumentException: invalid quantity
~~~

**Câu hỏi:** Dòng nào chắc chắn là Unified Logging theo định dạng thông dụng? Dòng nào chắc chắn dùng SLF4J?

**Đáp án:** Dòng thứ hai giống đầu ra Unified Logging nhờ decorator level/tag *gc*. Dòng thứ nhất giống application log nhưng **không thể kết luận chắc dùng SLF4J** chỉ từ text; JUL, Log4j2 hoặc custom formatter cũng có thể in tương tự. Dòng thứ ba là dòng đầu của exception stack/Thông báo Throwable, chưa xác định producer/đích xuất nếu thiếu ngữ cảnh.

### Bài 2 – Các selector

**Câu hỏi:** *gc+heap=debug* có nghĩa là “bật gc và heap riêng biệt ở debug” không?

**Đáp án:** Không. Dấu + tạo một **tag set kết hợp**; không wildcard, selector chọn chính xác tag set tương ứng. Muốn nhiều selector thì dùng dấu phẩy, còn muốn những tập tag chứa *gc* thì dùng wildcard *gc\**.

### Bài 3 – Không thấy GC

Bật *-Xlog:gc=info* cho chương trình chạy vài mili giây. Không có một dòng GC info nào. **Có kết luận JVM không hoạt động?**

**Đáp án:** Không. Có thể quá trình chạy không phát sinh GC event thỏa selector, collector/output khác, launch arg sai vị trí hoặc cách log khác theo build. Cần xác minh launch config, output và sự kiện.

### Bài 4 – Cùng stdout

Container stdout có cả dòng application JSON và dòng *[info][gc]*. Đội vận hành muốn bỏ GC debug nhưng giữ application INFO. **Điều chỉnh ở đâu?**

**Đáp án:** Ở **JVM Unified Logging selector/level** và output liên quan. Không hạ logger app INFO nếu chỉ muốn bớt GC. Trường hợp cần chỉnh runtime phải kiểm tra hỗ trợ *VM.log* và quyền; nếu cấu hình qua startup phải rollout có kiểm soát.

### Bài 5 – Cùng một thời điểm có phải cùng nguyên nhân?

Request mất 1.400 ms, trong thời gian đó có một GC pause 6 ms. **Có thể nói GC giải thích toàn bộ latency?**

**Đáp án:** Không. Pause 6 ms tự nó không giải thích toàn bộ 1.400 ms. Cần kiểm tra có nhiều pause, CPU/scheduling, queue wait và trace từng dependency; cùng một thời điểm chỉ cho thấy sự trùng lặp, không đủ chứng minh cơ chế.

### Bài 6 – Không thấy stack trace

Mã chỉ gọi logger với *ex.getMessage()* và collector hiển thị một dòng ERROR. **Thiếu stack có chứng minh exception không mang stack không?**

**Đáp án:** Không. Do mã không truyền Throwable, formatter không in stack hoặc log pipeline truncate; cần kiểm tra vị trí log và cấu hình. Có thể ghi *logger.log(Level.SEVERE, message, ex)* với JUL hoặc lời gọi tương đương của framework, theo policy bảo mật.

### Bài 7 – Uptime 3.000 giây

GC log có decorator *[3000.000s]*, application log có timestamp 10:05:00 UTC. **Chúng có cùng thời điểm nếu chỉ nhìn hai số này?**

**Đáp án:** Chưa đủ dữ liệu. Cần mốc JVM start time hoặc decorator time/utctime, đúng PID và clock của instance; uptime không phải giờ lịch.

## 16. Checklist tóm tắt cho incident report

Trước khi kết luận từ log:

- **Nguồn:** application code/framework, JVM UL, stderr stack trace hay container/OS?
- **Đích xuất:** stdout, stderr, file, collector nào? Có rotation/drop/truncation?
- **Phạm vi:** đúng instance/pod/PID/version, route và request không?
- **Thời gian:** event time hay ingestion time; UTC hay uptime?
- **Mức chi tiết:** logger level/appender của ứng dụng hay tag/level/decorator của -Xlog?
- **Bằng chứng:** app event/stack liên quan request, VM event và duration, metric và trace có khớp không?
- **Giới hạn:** log có thể thiếu vì sampling, thiếu instrumentation, không xảy ra sự kiện hoặc mất pipeline?
- **An toàn:** đổi log level có overhead, dữ liệu nhạy cảm, thời hạn bật/tắt, quyền và khả năng hoàn nguyên?

Một mẫu kết luận có căn cứ:

> Trong khoảng 08:10–08:15 UTC, requestId r-42 trên pod checkout-v2-7 có timeout ở payment call theo application log/trace. JVM UL cùng PID ghi hai GC pause 4 ms và 6 ms, không đủ để giải thích request 1,2 s. Giả thuyết ưu tiên: downstream latency hoặc connection wait; bước kiểm chứng: dependency spans, pool gauges và retry metrics. Chưa có bằng chứng kết luận GC là nguyên nhân.

## 17. Tài liệu chính thức để đối chiếu với JDK thực tế

- **Oracle JDK 21 – The java Command**, phần *Enable Logging with the JVM Unified Logging Framework*: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
- **Oracle JDK 21 – The jcmd Command**, diagnostic command *VM.log*: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- **OpenJDK JEP 158 – Unified JVM Logging**: https://openjdk.org/jeps/158
- **Java SE 17 – java.util.logging API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/package-summary.html

Luôn kiểm tra *java -Xlog:help* và *jcmd PID help VM.log* trên **chính build JVM** được chẩn đoán; tag, output và command khả dụng có thể thay đổi theo version/vendor.

## Ghi nhớ

**Application logging** trả lời “ứng dụng và request đang làm gì, nghiệp vụ gặp lỗi ở đâu?”; **JVM Unified Logging** trả lời “máy ảo đang làm gì, có sự kiện GC/safepoint/class/runtime nào?”. Cả hai có thể đổ về stdout nhưng **không cùng bộ phát, bộ lọc hoặc ngữ cảnh**. Stack trace có thể đến từ logger hoặc stderr và **không đồng nghĩa với -Xlog**. Khi chẩn đoán, phân biệt producer, ghi đúng instance/PID và thời điểm, phối hợp application log với Unified Logging, metric, trace/JFR, rồi kiểm chứng giả thuyết thay vì suy diễn nguyên nhân từ một dòng log.