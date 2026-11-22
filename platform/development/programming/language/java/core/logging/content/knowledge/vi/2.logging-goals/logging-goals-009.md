# Chi phí của logging trong Java

## 1. Logging mang lại giá trị nhưng tiêu tốn tài nguyên

Logging giúp truy vết sự kiện, tìm lỗi, giải thích biến động trạng thái và theo dõi vận hành. Đổi lại, một bản ghi có thể trải qua nhiều công đoạn: đánh giá biểu thức, lọc mức, tạo đối tượng log, định dạng thông điệp, truyền đến handler/appender, ghi file/console/network, rồi lưu trữ và lập chỉ mục. Các công đoạn này dùng **CPU, bộ nhớ, I/O, băng thông, dung lượng lưu trữ và thời gian xử lý request**.

Chi phí phụ thuộc vào tần suất phát log, độ lớn thông điệp, mức log, loại formatter, đường ghi đồng bộ/bất đồng bộ, hệ thống thu thập và tải thực tế. Vì vậy không có đáp án phổ quát như “một dòng log tốn X ms”. Mục tiêu thiết kế là giữ những dấu vết thực sự giúp chẩn đoán, đồng thời kiểm soát lượng tài nguyên phải trả.

Một phép đánh giá có ích cần trả lời:

- Bao nhiêu **sự kiện log/giây** được tạo trên mỗi instance và toàn bộ hệ thống?
- Khi log level bị tắt, chương trình có vẫn **tính đối số, ghép chuỗi hoặc serialize object** không?
- Khi bật log, phần nào diễn ra trên **thread phục vụ request** và phần nào trên thread xử lý log?
- Mỗi sự kiện tốn bao nhiêu **byte thực tế** khi ghi và lưu trữ? Lưu bao lâu? Có nhân bản/index không?
- Khi đích ghi chậm, hệ thống **chờ, tăng bộ nhớ, retry hay làm rơi log**?
- Các sự kiện đang ghi có giúp khôi phục được bối cảnh của lỗi hoặc theo dõi điều kiện vận hành không?

## 2. Chi phí nằm ở đâu trong đường đi của một bản ghi?

~~~text
Mã nghiệp vụ
  -> tính tham số của lời gọi log (Java đánh giá đối số)
  -> kiểm tra mức và bộ lọc tại logger
  -> tạo record, lấy timestamp/thread/context/Throwable
  -> formatter hoặc encoder chuyển sang text/JSON
  -> handler/appender; ghi trực tiếp hoặc đưa vào hàng đợi
  -> console, file, log driver hay collector qua mạng
  -> nén, lập chỉ mục, lưu giữ, truy vấn
~~~

**Sơ đồ là mô hình khái quát.** Framework khác nhau có thể hoán đổi các công đoạn; formatter có thể chạy trên thread ứng dụng hoặc worker tùy cấu hình, và lọc ở handler có thể diễn ra sau khi thông điệp được tính.

| Thành phần | Chi phí có thể phát sinh | Dấu hiệu |
| --- | --- | --- |
| Tạo thông điệp | Nối chuỗi, gọi `toString()`, dựng JSON, đọc các giá trị đắt tiền | CPU/allocations tăng dù log level bị tắt |
| Record và metadata | Object trung gian, timestamp, caller location, stack trace, context | Heap/GC tăng, profiler thấy formatter hoặc stack inspection |
| Đồng bộ hóa | Tranh chấp khóa, flush, dùng chung output stream | Thread bị chặn, throughput thấp dưới tải |
| I/O | Ghi console/file, đồng bộ đĩa, rotation/nén, gửi mạng | Disk/network tăng, latency p95/p99 kéo dài |
| Queue bất đồng bộ | Enqueue/dequeue, giữ nhiều object chờ ghi, backpressure | Queue depth tăng, GC hoặc dropped events |
| Hệ thống log tập trung | Ingestion, parsing, indexing, replication, retention | Số GB lưu và phí truy vấn/ingest tăng |
| Dữ liệu dư thừa | Bản ghi trùng, log mỗi vòng lặp, payload quá lớn | Tín hiệu quan trọng bị lẫn trong “nhiễu” |

Đừng chỉ đo CPU của ứng dụng. Khi log được đẩy sang collector hoặc worker async, chi phí có thể chuyển khỏi thread gọi nhưng vẫn tồn tại ở hệ thống khác.

## 3. Log bị tắt chưa chắc đã “miễn phí”

### 3.1. Đối số của lời gọi được tính trước

Trong Java, biểu thức truyền vào phương thức được đánh giá trước khi gọi phương thức đó:

~~~java
// Minh họa trong một phương thức đã có LOG và order.
LOG.fine("order=" + expensiveOrderDescription(order));
~~~

Nếu `FINE` đang tắt, logger sẽ không phát bản ghi nhưng `expensiveOrderDescription(order)` đã chạy rồi. Nó có thể gọi `toString()` đắt tiền, tính toán, tải dữ liệu hoặc tạo chuỗi lớn.

Cùng vấn đề với tham số:

~~~java
// Java Util Logging (JUL):
LOG.log(Level.FINE, "order={0}", expensiveOrderDescription(order));
~~~

Cơ chế placeholder có thể trì hoãn **định dạng** sự kiện, nhưng tham số `expensiveOrderDescription(order)` vẫn được Java tính trước khi lời gọi `LOG.log(...)` bắt đầu. Nguyên tắc này cũng đúng khi dùng API logging ngoài JDK như SLF4J: cú pháp placeholder không khiến biểu thức tham số tự động lazy.

### 3.2. Kiểm tra mức hoặc dùng Supplier

Nếu chỉ cần tính thông điệp khi mức cho phép:

~~~java
// Minh họa trong phạm vi có LOG và order:
if (LOG.isLoggable(Level.FINE)) {
    LOG.fine("order=" + expensiveOrderDescription(order));
}

// JUL hỗ trợ Supplier<String> từ Java 8:
LOG.fine(() -> "order=" + expensiveOrderDescription(order));
~~~

`Logger.isLoggable(Level.FINE)` tránh thực hiện nhánh khi mức không được chấp nhận. Overload nhận `Supplier<String>` chỉ gọi lambda khi mức logger phù hợp. Dùng cách này cho thông điệp đắt tiền; với chuỗi cố định ngắn, tối ưu có thể không đáng kể.

**Không nhét side effect vào lambda tạo log.** Không cập nhật dữ liệu, gọi API thay đổi trạng thái hoặc thực hiện kiểm tra nghiệp vụ bắt buộc trong `Supplier`: nếu log bị tắt, lambda không chạy. Log là hoạt động quan sát, không phải bước bắt buộc để mã nghiệp vụ đúng.

JUL có thể lọc **hai tầng**: logger và handler. Nếu logger chấp nhận `FINE` nhưng handler chỉ chấp nhận `INFO` trở lên, quá trình tạo record/thông điệp vẫn có thể xảy ra trước khi handler lọc bỏ. Vì vậy cần đối chiếu cả logger level và handler level, không chỉ nhìn các dòng xuất hiện trên console.

### 3.3. Ví dụ độc lập chạy trên Java 17+

Tạo tệp **LoggingCostDemo.java**:

~~~java
import java.util.logging.Level;
import java.util.logging.Logger;

public class LoggingCostDemo {
    private static final Logger LOG =
            Logger.getLogger(LoggingCostDemo.class.getName());

    private static int detailBuilds = 0;

    private static String buildDetails() {
        detailBuilds++;
        return "payload=" + "abcd".repeat(4);
    }

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO); // FINE bị vô hiệu hóa.

        LOG.fine("eager: " + buildDetails());
        LOG.fine(() -> "lazy: " + buildDetails());

        if (LOG.isLoggable(Level.FINE)) {
            LOG.fine("guarded: " + buildDetails());
        }

        System.out.println("detailBuilds=" + detailBuilds);
        System.out.println("fineEnabled=" + LOG.isLoggable(Level.FINE));
    }
}
~~~

Biên dịch và chạy tại thư mục chứa tệp:

~~~bash
javac -encoding UTF-8 LoggingCostDemo.java
java LoggingCostDemo
~~~

Kết quả **stdout** chính xác:

~~~text
detailBuilds=1
fineEnabled=false
~~~

Lời gọi đầu tính `buildDetails()` trước khi lọc nên tăng bộ đếm từ 0 lên 1. Lambda và nhánh kiểm tra mức không gọi `buildDetails()` vì `FINE` tắt. Hai dòng stdout đến từ `System.out.println` dùng cho bài tập, không phải từ logger. Ví dụ đã tắt parent handlers và không gắn handler khác, nên không có log được phát ra màn hình.

Nếu đổi `LOG.setLevel(Level.INFO)` thành `Level.FINE`, cả ba biểu thức tạo thông điệp đều được chạy và `detailBuilds=3`, `fineEnabled=true`. Dù vậy, không tự nhiên có log hiển thị khi chưa cấu hình handler. Bài học: **chi phí tạo sự kiện** và **chi phí xuất sự kiện** là hai phần cần xem riêng.

## 4. Những chi phí khi log thực sự được bật

### 4.1. CPU, object và garbage collection

Ghi `INFO`/`DEBUG` có thể yêu cầu dựng message, tính các trường metadata, trích thông tin exception, xử lý ngữ cảnh request và mã hóa JSON/text. Nhiều lời gọi trong vòng lặp tạo chuỗi, mảng tham số và record ngắn hạn, tăng tốc độ cấp phát, dẫn tới GC chạy thường xuyên hơn. Ghi nguyên object có thể kích hoạt `toString()` tốn kém hoặc chứa dữ liệu không cần thiết.

Một stack trace dài tạo nhiều dữ liệu và chi phí định dạng. Nếu cùng exception bị ghi ở nhiều lớp rồi ném tiếp, ứng dụng vừa tạo log trùng vừa gây khó nhận ra điểm xử lý lỗi thật. Ưu tiên ghi exception có ngữ cảnh ở ranh giới chịu trách nhiệm báo cáo lỗi; các tầng còn lại chỉ bổ sung thông tin khi cần.

Với formatter, việc thêm class/method/line của caller có thể đòi hỏi kiểm tra stack; với cấu hình async, cần xem framework thu thập thông tin này lúc nào. Không nên bật đầy đủ thông tin caller cho mọi log trên hot path nếu không có nhu cầu cụ thể.

### 4.2. I/O và độ trễ

Log ra stdout trong container vẫn đi qua output stream và log driver; log ra file vẫn cần ghi đĩa, rotation và có thể nén; log qua network cần serialize, gửi dữ liệu, retry hoặc batch. Sink bị chậm có thể kéo dài **độ trễ đuôi p95/p99** dù chi phí trung bình của một dòng nhỏ.

“Synchronous” không có nghĩa mọi dòng chắc chắn được `fsync` xuống đĩa ngay; nhiều handler dùng buffering. Còn “asynchronous” không có nghĩa không tốn I/O: công việc chỉ được chuyển sang thread khác hoặc thời điểm khác.

### 4.3. Dung lượng, chỉ mục và retention

Mỗi sự kiện chiếm byte trên wire và tại đích lưu trữ. Tổng chi phí phụ thuộc số event, byte/event, thời gian giữ, bản sao, cách nén, các chỉ mục và truy vấn. Với dữ liệu cấu trúc, các trường có nhiều giá trị duy nhất (ví dụ request ID) có thể làm công việc index/search đắt hơn, tùy giải pháp thu thập. Không nên ghi hàng nghìn field chỉ vì hệ thống hỗ trợ JSON.

## 5. Đồng bộ và bất đồng bộ: ưu điểm và đánh đổi

### Đồng bộ

Một handler/appender đồng bộ thực hiện công việc ghi trên đường xử lý của thread gọi. Khi sink chậm, thread nghiệp vụ có thể phải chờ formatter, lock hoặc I/O; điều này trực tiếp ảnh hưởng throughput và latency. Đường đi đồng bộ thường đơn giản hơn để quan sát, nhưng cần đo trong tải đồng thời và khi collector/file system gặp sự cố.

### Bất đồng bộ

Async logger/appender thường đưa sự kiện vào hàng đợi, để worker xử lý phần encode/ghi sau. Điều này **có thể giảm thời gian chờ của request** và tạo điều kiện batch I/O, nhưng không xóa chi phí CPU, bộ nhớ hay lưu trữ. Còn có các rủi ro:

- **Queue có giới hạn:** khi đầy, tùy thư viện và cấu hình sẽ block, drop, ghi trên thread gọi hoặc dùng chính sách khác. Không được giả định một hành vi chung cho mọi appender.
- **Queue quá lớn:** tăng lượng object giữ trong heap, thời gian chờ log và áp lực GC; queue không giới hạn có thể làm cạn bộ nhớ.
- **Crash/kill:** bản ghi còn trong queue/buffer có thể chưa tới đích. Shutdown hook và flush giúp giảm nguy cơ nhưng không tạo bảo đảm bền vững tuyệt đối.
- **Ngữ cảnh thread:** dữ liệu như MDC của một framework có thể phải được chụp vào record; không phải mọi thread-local tự chuyển sang worker.
- **Lỗi hệ thống thu log:** nếu không giám sát độ sâu queue, số event bị bỏ và thời gian drain, ứng dụng có thể chạy “nhanh” nhưng mất dấu vết đúng lúc cần điều tra.

Ví dụ: service xử lý request khoảng 10 ms nhưng sink log thỉnh thoảng bị chặn 40 ms. Async có thể giảm ảnh hưởng trực tiếp lên request, nhưng nếu tốc độ phát event lâu dài lớn hơn tốc độ consume, queue cuối cùng vẫn đầy. Thiết kế phải nêu rõ mức độ ưu tiên giữa độ trễ nghiệp vụ và việc giữ log.

Nếu một loại sự kiện cần **bảo toàn theo yêu cầu đối soát/audit**, cần thiết kế đường ghi đáng tin phù hợp với yêu cầu đó, không tự coi một hàng đợi logger trong bộ nhớ là kho lưu trữ chắc chắn.

## 6. Ước lượng chi phí theo tần suất

Đặt:

- `R` = số sự kiện log mỗi giây **sau lọc và sampling**.
- `S` = số byte trung bình của một bản ghi đã encode, gồm các trường cần ghi.
- `T` = tổng số giây lưu dữ liệu.
- `K` = số bản sao dữ liệu gốc nếu cơ chế lưu trữ nhân bản.

Công thức ước lượng:

~~~text
Bytes/giây = R × S
Bytes lưu gốc ≈ R × S × T
Bytes cho K bản sao, trước nén và index ≈ R × S × T × K
~~~

Giả sử một hệ thống ghi **1.000 sự kiện/giây**, trung bình **250 byte UTF-8/sự kiện**, giữ **30 ngày**:

~~~text
1.000 × 250 = 250.000 byte/giây
250.000 × 86.400 = 21.600.000.000 byte/ngày
21.600.000.000 × 30 = 648.000.000.000 byte/30 ngày
                         = 648 GB theo đơn vị thập phân
~~~

Ba bản sao đầy đủ tương đương khoảng **1.944 GB (1,944 TB)** dữ liệu gốc trước nén và indexing. Con số chỉ là phép tính minh họa, không phải hóa đơn: việc nén, replication, metadata, tính phí ingestion, truy vấn, chuyển tầng dữ liệu và retention làm kết quả thực tế khác đi.

**Byte khác ký tự.** Một String Java đếm theo đơn vị UTF-16, nhưng log thường được encode thành UTF-8. Ký tự tiếng Việt có thể dùng nhiều byte; JSON còn có tên trường, dấu phân cách và escape. Hãy đo kích thước log sau encode hoặc từ hệ thống thu thập, thay vì lấy số lượng ký tự trong source code.

Nếu giảm tần suất còn 10% bằng việc loại bỏ/sampling những bản ghi DEBUG không thiết yếu, lượng dữ liệu của **nhóm bản ghi đó** giảm tương ứng (khi kích thước trung bình giữ nguyên). Không suy diễn tổng chi phí toàn hệ thống giảm 90% nếu các loại log khác vẫn được giữ và có chi phí cố định.

## 7. Giảm chi phí mà vẫn điều tra được sự cố

### 7.1. Ghi đúng mức và đúng sự kiện

- Dùng mức tương ứng với ý nghĩa sự kiện. JUL có `SEVERE`, `WARNING`, `INFO`, `CONFIG`, `FINE`, `FINER` và `FINEST`; framework khác có thể dùng `ERROR`, `WARN`, `DEBUG`, `TRACE`.
- Ở `INFO`, ưu tiên mốc trạng thái quan trọng (khởi động, kết thúc job, kết quả thao tác lớn); tránh mặc định in mỗi vòng lặp, mỗi row hoặc toàn bộ payload của mọi request.
- Ở mức chi tiết như `FINE/DEBUG/TRACE`, chỉ bật trong phạm vi và thời gian cần điều tra, cân nhắc giới hạn số bản ghi.
- Với sự kiện lặp thường xuyên, **metric counter/histogram** có thể thể hiện số lần xảy ra và độ trễ tốt hơn hàng triệu dòng văn bản. Log vẫn có giá trị để giữ ngữ cảnh của sự kiện cụ thể.
- Không lặp lại cùng một exception qua nhiều tầng nếu không có thêm thông tin mới.

Không có quy tắc bắt buộc mọi API phải ghi access log từng request bằng cùng một mức; yêu cầu quan sát và khối lượng phụ thuộc ứng dụng.

### 7.2. Tránh việc tính dữ liệu log không cần thiết

Dùng Supplier, `isLoggable` hoặc tính toán có điều kiện khi thông điệp đắt. Parameterized logging giảm công định dạng nhưng không trì hoãn đánh giá mọi đối số. Nếu một object quá lớn, chỉ ghi trường cần thiết như `operation`, `requestId`, `outcome`, `durationMs` và mã lỗi an toàn.

Đừng serialize toàn bộ object hoặc gọi `toString()` đắt tiền để tạo thông điệp mặc định. Với object ORM, `toString()` có thể truy cập thuộc tính hoặc quan hệ không mong muốn; không nên phụ thuộc vào side effect để in log.

### 7.3. Quản lý log volume và kích thước

Có thể dùng sampling, rate limiting hoặc gom báo cáo lặp: chẳng hạn thay vì log một cảnh báo cho mỗi lần retry, ghi số lần retry cuối cùng, nguyên nhân và kết quả. Sampling có đánh đổi: lỗi hiếm có thể không được ghi. Đối với sự kiện bắt buộc lưu đầy đủ, phải chọn chính sách riêng theo yêu cầu tin cậy.

Thiết lập rotation, retention, compression và index policy phù hợp. Tránh các trường có nhiều giá trị duy nhất nếu không phục vụ truy vấn hữu ích. Phân biệt log kỹ thuật để debug tạm thời với dữ liệu báo cáo vận hành cần giữ lâu dài.

### 7.4. Kiểm soát backpressure và bảo mật

Khi dùng async, chọn queue hữu hạn, ngưỡng cảnh báo và hành vi lúc đầy rõ ràng. Đo **queue depth**, **enqueue/block time**, **dropped events** và thời gian flush ở shutdown. Thử cả lúc sink không phản hồi.

Không ghi password, token, session cookie, bí mật ứng dụng, hoặc thông tin cá nhân quá mức cần thiết. Chỉ chọn trường an toàn ngay tại nơi phát log thường dễ kiểm soát hơn ghi toàn bộ rồi regex che lại. Che dữ liệu cũng có chi phí CPU và có thể bỏ sót trường mới; không vì tiết kiệm hiệu năng mà bỏ yêu cầu bảo vệ dữ liệu.

## 8. Cách đo chi phí logging đúng hơn

Một phép đo hữu ích nên có **baseline** và các cấu hình so sánh dưới cùng workload, cùng phiên bản JDK, máy, chính sách GC và hệ thống thu log:

| Trường hợp | Mục đích |
| --- | --- |
| Mức DEBUG/FINE bị tắt | Đo chi phí còn lại ở lời gọi, đánh giá đối số và lọc |
| Mức chi tiết bật, handler rất nhẹ | Ước lượng chi phí tạo record/format trong JVM |
| Mức chi tiết bật, sink giống production | Đo thêm console/file/network/collector thật |
| Async với queue cấu hình cụ thể | Xem latency request, backlog, GC, drop/block |
| Ít trường hoặc sampling | Xem mức giảm volume/chi phí và khả năng chẩn đoán còn đủ không |

Theo dõi **throughput request/s, p50/p95/p99 latency, CPU, allocation rate, heap/GC, disk bytes, network bytes, log events/s, byte/event, queue depth, dropped events** và nếu có thì ingestion/storage cost. Đo hiệu năng nhưng cũng xác nhận ứng dụng vẫn hoạt động đúng.

Cách tiến hành:

1. Tạo tải đại diện cho thực tế: nhiều request đồng thời, payload khác kích thước, tỷ lệ thành công/thất bại và số exception phù hợp.
2. Warm up JVM để tránh nhầm ảnh hưởng class loading/JIT với logging. Giữ nguyên cấu hình môi trường trong từng lần so sánh.
3. Chạy nhiều lần, so sánh phân phối kết quả thay vì dựa vào một lần nhanh/chậm. Xác định xem sink hoặc collector có đang là nút cổ chai không.
4. Dùng **Java Flight Recorder (JFR)** hoặc profiler để tìm CPU, cấp phát, GC, lock contention. Nếu muốn đo riêng một thao tác nhỏ của Java, dùng công cụ microbenchmark thích hợp như **JMH**; vòng lặp `System.nanoTime()` tự viết dễ bị nhiễu bởi JIT, tối ưu hóa và môi trường.
5. Thử trạng thái sink chậm/ngắt kết nối, queue đầy và shutdown. Một cấu hình chạy tốt khi bình thường có thể làm tăng p99 hoặc mất log khi sự cố xảy ra.

**Chú ý:** `LOG.info(...)` trả về nhanh không chứng minh toàn bộ logging rẻ. Async đẩy phần việc sang thread khác; buffering dồn I/O về sau. Ngược lại, benchmark in trực tiếp vào console của IDE có thể bị ảnh hưởng bởi giao diện hiển thị, không đại diện production.

## 9. Tình huống áp dụng

### A. Log bên trong vòng lặp lớn

Một job xử lý **500.000 bản ghi** và mỗi bản ghi tạo một log 200 byte: một lần chạy đã xuất khoảng **100 MB dữ liệu gốc**, chưa tính metadata, index và bản sao. Nếu việc này lặp liên tục, log volume có thể vượt xa giá trị chẩn đoán.

Hướng phù hợp: ghi `jobId`, thời điểm bắt đầu/kết thúc, số lượng thành công/thất bại và duration; dùng metrics cho tổng số/tốc độ. Chỉ bật thông tin chi tiết theo ID, mẫu dữ liệu hoặc thời gian điều tra. Khi cần tìm record lỗi, ghi ID và nguyên nhân của lỗi thực thay vì mọi record hợp lệ.

### B. Log collector quá tải

API phát 15.000 event/s nhưng consumer xử lý được 12.000 event/s trong thời gian dài. Backlog tăng trung bình **3.000 event/s**, nên một queue 10.000 event (ban đầu trống) có thể đầy sau khoảng **3,33 giây** nếu không có biến động và không có cơ chế điều tiết. Khi queue đầy, ứng dụng có thể chậm hoặc mất log tùy chính sách. Giảm những event ít giá trị, tăng năng lực sink, giới hạn queue và đặt cảnh báo cho backlog/drop cần được cân nhắc đồng thời.

## 10. Sai lầm phổ biến

| Sai lầm | Hệ quả | Cách làm |
| --- | --- | --- |
| Nghĩ mức log tắt nghĩa là không tốn tài nguyên | Đối số vẫn được đánh giá, tạo chuỗi | Dùng lazy/guard khi thông điệp đắt |
| Dùng placeholder rồi tin mọi tham số đều lazy | Gọi hàm tốn CPU trước lời gọi logger | Tránh biểu thức đắt hoặc guard theo mức |
| Ghi `INFO` trong vòng lặp nóng | CPU/I/O/lưu trữ tăng đột biến | Metrics, log theo giai đoạn hoặc sampling |
| Ghi object/Throwable quá lớn hoặc trùng lặp | Tăng allocation, byte/s, khó đọc | Ghi trường và stack trace đúng vị trí |
| Cho rằng async luôn nhanh và không mất dữ liệu | Queue có thể đầy; crash gây loss | Đo backpressure/drop và thiết kế độ bền phù hợp |
| Chỉ đo thời gian `LOG.info` | Bỏ qua worker, I/O, indexing, retention | Đo toàn hệ thống và p95/p99 |
| Coi stdout là miễn phí | Console/log driver vẫn có I/O | Kiểm thử với đích ghi thật |
| Ghi secret để tiện debug | Rủi ro lộ dữ liệu qua pipeline log | Ghi trường an toàn, giới hạn truy cập/retention |

## 11. Bài tập tự kiểm tra

1. Chạy **LoggingCostDemo.java**, đổi `Level.INFO` thành `Level.FINE` và giải thích vì sao bộ đếm chuyển từ `1` sang `3`, dù chương trình vẫn không có handler in dòng log.
2. Với 2.000 sự kiện/s, 500 byte/sự kiện và retention 7 ngày, ước lượng số GB dữ liệu gốc theo đơn vị thập phân. Nếu 80% là DEBUG có thể sampling, tính lại khi chỉ giữ 10% **của nhóm DEBUG** và giữ nguyên các log còn lại.
3. Đối với queue phát 15.000 event/s và ghi được 12.000 event/s, mô tả hành vi khi đầy với ba chính sách block, drop và ghi đồng bộ dự phòng. Chính sách nào ảnh hưởng latency, chính sách nào có thể mất dữ liệu?
4. Lập kế hoạch so sánh INFO, DEBUG, DEBUG dùng Supplier/sampling trên cùng API: xác định workload, chỉ số p95/p99, CPU/GC, byte/s, queue depth và khả năng tái hiện lỗi, rồi nêu tiêu chí chọn cấu hình.

**Kết luận kiến thức:** chi phí logging gồm cả việc tạo thông điệp khi mức tắt, xử lý record khi mức bật, I/O và chi phí của pipeline lưu trữ. Cách tối ưu đáng tin là **ghi đúng sự kiện, tính dữ liệu có điều kiện, kiểm soát volume/queue, và đo với workload thực tế**.