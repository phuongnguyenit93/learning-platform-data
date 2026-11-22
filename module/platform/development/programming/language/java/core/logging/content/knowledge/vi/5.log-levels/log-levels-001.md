# TRACE — mức log chi tiết nhất để theo dõi luồng thực thi trong Java

## 1. TRACE là gì?

**TRACE** là mức logging dành cho những thông tin kỹ thuật rất chi tiết về các bước bên trong quá trình xử lý: một phương thức đã nhận tham số gì, đang xét nhánh điều kiện nào, trạng thái trung gian biến đổi ra sao, một vòng lặp đã đi qua phần tử nào, hoặc một lần retry đã diễn ra ở bước nào. TRACE đặc biệt hữu ích khi cần dựng lại **trình tự thực thi** của một tình huống lỗi mà log thông thường chưa cung cấp đủ manh mối.

TRACE không nhất thiết mô tả một lỗi. Một dòng TRACE có thể ghi lại hoạt động hoàn toàn bình thường, chẳng hạn “đã chọn nhánh cache hit” hay “đã bỏ qua phần tử không hợp lệ”. Ý nghĩa của nó nằm ở **độ chi tiết chẩn đoán**, không phải độ nghiêm trọng của sự kiện.

Ví dụ minh họa luồng kiểm tra một đơn hàng:

~~~text
TRACE requestId=r-17 operation=checkout step=validate-items itemCount=2
TRACE requestId=r-17 operation=checkout step=stock-check itemId=sku-12 available=true
TRACE requestId=r-17 operation=checkout step=discount rule=NEW_CUSTOMER matched=false
TRACE requestId=r-17 operation=checkout step=calculate-total totalCents=125000
INFO  requestId=r-17 operation=checkout outcome=success
~~~

Đây là **dữ liệu log minh họa**, không phải stdout của một chương trình bên dưới. Các dòng TRACE giúp tìm chính xác bước xử lý; dòng INFO tóm tắt kết quả mà người vận hành cần biết khi hoạt động bình thường.

**Phân biệt tên gọi:** mức log TRACE không đồng nghĩa với *distributed tracing*. Distributed tracing dùng trace/span ID và các span để theo dõi request đi qua nhiều dịch vụ; đặt log level thành TRACE **không tự động tạo span hoặc trace phân tán**. Log ở mức TRACE có thể được gắn `traceId`/`spanId` khi hệ thống có cơ chế truyền ngữ cảnh, nhờ đó hai loại dữ liệu bổ sung cho nhau.

## 2. Vị trí của TRACE trong hệ thống log level

Trong các hệ thống phổ biến dùng **SLF4J + Logback** hoặc **Log4j 2**, thứ tự mức thường gặp từ ít nghiêm trọng/chi tiết nhất đến nghiêm trọng nhất là:

~~~text
TRACE -> DEBUG -> INFO -> WARN -> ERROR
nhiều chi tiết hơn          ít chi tiết hơn
~~~

Các thư viện khác nhau còn có thể có mức khác (chẳng hạn `FATAL` ở một số hệ thống), nên không coi danh sách trên là chuẩn bắt buộc của mọi API.

Khi đặt ngưỡng logger ở `TRACE`, về nguyên tắc logger sẽ chấp nhận cả TRACE và những mức nghiêm trọng hơn như DEBUG, INFO, WARN, ERROR; **việc bản ghi có thực sự xuất ra còn phụ thuộc filter và appender/handler**. Khi đặt ngưỡng `INFO`, các mức TRACE và DEBUG thông thường bị loại.

| Mức | Câu hỏi chính cần trả lời | Ví dụ phù hợp |
| --- | --- | --- |
| TRACE | *Chương trình đi qua những bước nhỏ nào?* | Nhánh `if` được chọn, giá trị trung gian đã chọn lọc, trạng thái trước/sau một bước |
| DEBUG | *Thành phần này vận hành ra sao ở mức đủ để gỡ lỗi?* | Cache miss, tham số truy vấn đã ẩn dữ liệu nhạy cảm, quyết định retry |
| INFO | *Sự kiện vận hành đáng nhớ nào đã xảy ra?* | Job hoàn tất, ứng dụng khởi động, tác vụ nghiệp vụ thành công |
| WARN | *Điều gì bất thường nhưng hệ thống còn tiếp tục được?* | Sử dụng fallback, nhận đầu vào có vấn đề, retry sau thất bại |
| ERROR | *Thao tác quan trọng nào thất bại?* | Không xử lý được request, không ghi được dữ liệu cần thiết |

Ranh giới TRACE và DEBUG là **quy ước thiết kế**, không phải một định nghĩa máy móc áp dụng cho mọi nhóm. Ví dụ, “cache miss” có thể là DEBUG trong dịch vụ ít tải nhưng chuyển thành TRACE khi nó xảy ra hàng triệu lần và chỉ cần trong điều tra chuyên sâu. Quan trọng là sự nhất quán và giá trị chẩn đoán.

### TRACE trong các API Java

- **SLF4J**: có `logger.trace(...)`, `logger.isTraceEnabled()` và từ SLF4J 2.x có fluent API `logger.atTrace()`. SLF4J là logging facade; để thật sự ghi log cần provider/backend phù hợp như Logback hoặc Log4j 2 binding.
- **Log4j 2 API**: có mức `TRACE` và phương thức `trace(...)`; cấu hình ngưỡng và appender quyết định đầu ra.
- **`System.Logger` của JDK 9+**: có `System.Logger.Level.TRACE` và `System.getLogger(...)`. Nó dùng hệ thống ghi log do `System.LoggerFinder` cung cấp; cách cấu hình, lọc và hiển thị cuối cùng phụ thuộc provider/backend được sử dụng.
- **`java.util.logging` (JUL)**: không có tên mức `TRACE` riêng; các mức chi tiết của JUL là `FINE`, `FINER`, `FINEST`. Chúng có mục đích gần với DEBUG/TRACE nhưng **không nên giả định ánh xạ một-một trong mọi bridge hoặc provider**.

Bài này sử dụng `System.Logger.Level.TRACE` trong ví dụ JDK 17 độc lập để thấy TRACE là mức có thật trong API Java chuẩn; phần cấu hình Logback minh họa trường hợp thường gặp ở ứng dụng dùng SLF4J.

## 3. Ghi nội dung gì ở mức TRACE?

Mỗi dòng TRACE nên trả lời được một câu hỏi cụ thể về luồng xử lý; có đủ ngữ cảnh để nối với các bản ghi liên quan, nhưng không phải bản sao toàn bộ bộ nhớ ứng dụng.

Các loại thông tin hay hữu ích:

1. **Điểm vào/ra ở phạm vi cần điều tra:** tên thao tác, ID tương quan, trạng thái kết thúc, thời gian của bước nhỏ nếu cần. Không buộc phải ghi mọi phương thức.
2. **Nhánh quyết định:** quy tắc kiểm tra nào được đánh giá, kết quả `true/false`, nhánh fallback hay đường đi chính được chọn.
3. **Giá trị trung gian có chọn lọc:** số lượng phần tử, trạng thái bộ đệm, chỉ số đang xét, khóa tra cứu đã được ẩn dữ liệu nhạy cảm, giới hạn dùng để so sánh.
4. **Các lần thử lại:** số lần thử, lý do quyết định thử lại, độ trễ chờ, trạng thái cuối của từng lần nếu việc đó có ích cho phân tích.
5. **Chuyển trạng thái:** từ `NEW` sang `VALIDATING`, hoặc từ `PENDING` sang `COMPLETED`, kèm ID đối tượng và nguyên nhân.
6. **Ranh giới giao tiếp quan trọng:** bước chuẩn bị/gửi/nhận từ cache, database, network; giữ tên thao tác và mã trạng thái phù hợp, tránh đưa bí mật hay payload nguyên vẹn.

Ví dụ nên chọn:

~~~text
TRACE requestId=req-5 step=select-rule rule=LIMITED_DISCOUNT eligible=false
TRACE requestId=req-5 step=retry attempt=2 maxAttempts=3 backoffMs=400
TRACE requestId=req-5 step=aggregate processedCount=200 rejectedCount=3
~~~

Các bản ghi có trường rõ tên thường dễ lọc và so sánh hơn dạng “here”, “checkpoint 1” hoặc “value changed”. Chuỗi dạng `key=value` chỉ là một kiểu minh họa; log có cấu trúc JSON cũng phù hợp nếu hệ thống thu thập hỗ trợ.

### Những thông tin không nên đưa vào TRACE

Không log password, API key, access token, session cookie, mã OTP, chuỗi kết nối chứa secret, nội dung cá nhân đầy đủ hay payload chưa được rà soát. **TRACE vẫn là log lưu trữ và vận chuyển được**, không phải vùng an toàn chỉ dành cho máy phát triển. Nếu cần nghiên cứu cấu trúc request, ghi field an toàn, số lượng phần tử, độ dài hoặc ID được phép dùng để tương quan.

Không gọi các phương thức có side effect để “lấy dữ liệu phục vụ TRACE”. Ví dụ, một truy vấn database hay lời gọi mạng bên trong thao tác dựng thông điệp có thể làm thay đổi hành vi ứng dụng và khiến việc debug sai lệch. Hạn chế ghi nguyên object lớn vì `toString()` có thể tạo hàng megabyte dữ liệu, truy cập dữ liệu không mong muốn hoặc chứa thông tin nhạy cảm.

## 4. Ví dụ Java 17 độc lập: TRACE theo từng bước

JDK 17 có `System.Logger` nên ví dụ sau **không cần thư viện bên ngoài**. Chương trình tính tổng các số chẵn và để TRACE mô tả từng quyết định tại vòng lặp.

Tạo tệp **TraceLevelDemo.java**:

~~~java
public class TraceLevelDemo {
    private static final System.Logger LOG =
            System.getLogger(TraceLevelDemo.class.getName());

    static int sumEven(int[] numbers) {
        int sum = 0;

        for (int i = 0; i < numbers.length; i++) {
            final int index = i;
            final int value = numbers[i];

            LOG.log(System.Logger.Level.TRACE,
                    () -> "step=inspect index=" + index + " value=" + value);

            if (value % 2 == 0) {
                sum += value;
                final int partialSum = sum;
                LOG.log(System.Logger.Level.TRACE,
                        () -> "step=accept index=" + index
                                + " partialSum=" + partialSum);
            } else {
                LOG.log(System.Logger.Level.TRACE,
                        () -> "step=skip index=" + index + " reason=odd");
            }
        }

        return sum;
    }

    public static void main(String[] args) {
        int result = sumEven(new int[] {1, 2, 3, 4});
        System.out.println("evenSum=" + result);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 TraceLevelDemo.java
java TraceLevelDemo
~~~

Kết quả nghiệp vụ ghi bằng `System.out.println` ra **stdout**:

~~~text
evenSum=6
~~~

**Lưu ý về đầu ra:** đoạn trên là stdout do chương trình chủ động in ra. Các dòng do `System.Logger` phát sinh, nếu được provider chấp nhận, có thể đi ra stderr, file hoặc đích khác với định dạng phụ thuộc cấu hình. Với cấu hình mặc định thường không bật mức TRACE, bạn có thể không thấy dòng TRACE nào. Do đó không khẳng định luôn có một transcript TRACE cố định khi chạy trên mọi máy.

Nếu TRACE được bật cho logger này, diễn biến mong đợi ở mức **nội dung thông điệp** là:

~~~text
step=inspect index=0 value=1
step=skip index=0 reason=odd
step=inspect index=1 value=2
step=accept index=1 partialSum=2
step=inspect index=2 value=3
step=skip index=2 reason=odd
step=inspect index=3 value=4
step=accept index=3 partialSum=6
~~~

Đây là các **message mô tả diễn biến** sau khi bỏ phần prefix/metadata của backend, không phải cam kết về định dạng console. Kết quả `6` là `2 + 4`. Giá trị `index`, `value` và `partialSum` được sao chép vào biến `final` để lambda có thể dùng; Java yêu cầu biến local capture bởi lambda phải là final hoặc *effectively final*.

Đoạn mã dùng overload nhận `Supplier<String>`, vì vậy phần nối chuỗi trong lambda chỉ cần được thực hiện khi mức TRACE được chấp nhận theo API. Cách này tránh tạo message vô ích khi TRACE bị tắt. Biểu thức nghiệp vụ `sum += value` vẫn được thực hiện dù logging bị tắt: **không đưa logic cốt lõi vào lambda log**.

## 5. TRACE thực tế với SLF4J và Logback

Nhiều ứng dụng Spring Boot hoặc Java server sử dụng SLF4J làm API và một logging backend để phát bản ghi. Đây là một lựa chọn phổ biến, nhưng **SLF4J không nằm sẵn trong JDK**; đoạn mã sau minh họa cách sử dụng khi dự án đã có SLF4J 2.x và provider tương thích.

Trong lớp ứng dụng:

~~~java
// Đoạn minh họa trong dự án đã có SLF4J; không độc lập nếu thiếu dependency.
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class OrderValidator {
    private static final Logger LOG =
            LoggerFactory.getLogger(OrderValidator.class);

    public boolean isValidQuantity(String requestId, int quantity) {
        LOG.trace("requestId={} step=check-quantity quantity={}",
                requestId, quantity);

        boolean valid = quantity > 0;
        LOG.trace("requestId={} step=check-quantity valid={}",
                requestId, valid);
        return valid;
    }
}
~~~

Mỗi thông điệp có mục đích rõ: trước khi đánh giá và sau khi có kết quả. Placeholder `{}` giúp backend định dạng tham số theo cơ chế của nó. Nếu `TRACE` bị lọc, một phần chi phí định dạng được tránh; **nhưng Java vẫn đánh giá biểu thức tham số trước khi gọi `trace(...)`**.

### Tập trung TRACE vào một package

Ví dụ cấu hình **logback.xml** cho ứng dụng dùng Logback:

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.checkout" level="TRACE"/>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

Khi các lớp nằm trong `com.example.checkout`, logger tương ứng có ngưỡng TRACE; những logger khác kế thừa ngưỡng INFO từ root nếu không có cấu hình riêng. Trong cấu hình minh họa này, sự kiện từ logger con đi tới appender qua cơ chế additivity; mức INFO của root không tự biến thành bộ lọc lại cho sự kiện đã được logger con chấp nhận. Nếu appender có filter riêng, filter đó vẫn có thể chặn TRACE.

Điểm cần nhớ: **bật TRACE cho một package nghi vấn** thường tốt hơn bật cho toàn bộ root logger. Một số framework nội bộ tạo rất nhiều bản ghi TRACE, khiến log dễ quá tải và chôn vùi sự kiện cần tìm. Cách đặt mức động qua file cấu hình, biến môi trường hoặc API quản trị phụ thuộc vào framework và ứng dụng; không mặc định một cú pháp áp dụng cho mọi stack.

### Viết TRACE có chi phí thấp khi bị tắt

Ví dụ **không tối ưu**:

~~~java
// Hàm expensiveDescription được thực thi dù TRACE có thể đang tắt.
LOG.trace("details={}", expensiveDescription(order));
~~~

Nếu việc tạo chuỗi rất tốn tài nguyên, dùng kiểm tra mức:

~~~java
if (LOG.isTraceEnabled()) {
    LOG.trace("details={}", safeDescription(order));
}
~~~

Trong **SLF4J 2.x**, fluent API còn hỗ trợ Supplier cho argument:

~~~java
LOG.atTrace()
   .addArgument(() -> safeDescription(order))
   .log("details={}");
~~~

Ba đoạn trên là mã **minh họa trong lớp đã có LOG và order**, không phải chương trình Java hoàn chỉnh. `safeDescription(...)` chỉ được dùng khi nó không có side effect và đã loại dữ liệu nhạy cảm. Supplier tránh dựng thông điệp/argument đắt khi TRACE không bật; nếu TRACE bật, thao tác đó vẫn có chi phí thật. Một lambda không tự làm cho chương trình nhanh hơn khi mọi bản ghi đều được chấp nhận.

Không dùng `toString()` trên toàn bộ object request, đặc biệt object chứa secret hoặc cấu trúc dữ liệu lớn. Hãy thiết kế formatter chỉ lấy các trường cần cho câu hỏi chẩn đoán.

## 6. TRACE, hiệu năng và khả năng quan sát

TRACE thường phát ra **nhiều bản ghi hơn DEBUG hoặc INFO** vì được đặt ở các bước nhỏ của thuật toán. Đặc biệt, TRACE trong vòng lặp, ở thư viện mạng, bộ phân tích dữ liệu hoặc thành phần retry có thể làm khối lượng log tăng nhanh.

Ví dụ: xử lý **10.000 request/giây**, mỗi request phát **8 dòng TRACE**, mỗi dòng trung bình **200 byte sau khi encode**:

~~~text
10.000 request/s × 8 event/request = 80.000 event/s
80.000 event/s × 200 byte        = 16.000.000 byte/s
16.000.000 × 86.400               = 1.382.400.000.000 byte/ngày
                                   = 1.382,4 GB/ngày (đơn vị thập phân)
~~~

Đây mới là dung lượng dữ liệu log thô theo giả định, **chưa** tính nén, index, replication, retry hoặc metadata của hệ thống thu thập. Nếu giữ 7 ngày, lượng dữ liệu thô đạt khoảng `9.676,8 GB`. Trong thực tế, byte trên wire, trong file và trong kho tìm kiếm có thể khác nhau. Không suy ra chi phí hóa đơn trực tiếp từ phép tính đơn giản này.

Các loại chi phí và tác động:

| Phần | Khi TRACE bật với lưu lượng lớn |
| --- | --- |
| CPU | Tạo chuỗi, format JSON, lấy caller/thread/context, định dạng stack trace |
| Heap/GC | Nhiều object log và byte buffer ngắn hạn hoặc hàng đợi chờ xử lý |
| I/O | Console, file và log collector nhận nhiều dữ liệu hơn |
| Latency | Handler đồng bộ có thể chặn thread nghiệp vụ; p95/p99 tăng |
| Async queue | Backlog tăng, buffer đầy, tùy chính sách có thể block hoặc drop |
| Storage | Ingest, index, retention và tìm kiếm tốn dung lượng/chi phí |
| Tính dễ đọc | Quá nhiều bản ghi chi tiết có thể làm khó xác định nguyên nhân lỗi |

**Async logging không xóa chi phí.** Nó có thể giảm thời gian chờ của thread gọi bằng cách đẩy một phần xử lý sang worker, nhưng hàng đợi có thể đầy khi tốc độ phát log lớn hơn tốc độ ghi. Khi đó hành vi phụ thuộc cấu hình appender: chờ, bỏ bản ghi, ghi dự phòng hoặc phương án khác. Không mặc định TRACE được lưu bền vững hoặc không bao giờ làm chậm ứng dụng.

Cần đo bằng workload gần production: throughput, p95/p99 latency, CPU, allocation/GC, bytes/s, hàng đợi và dropped events. So sánh trước/sau khi bật TRACE **trên cùng lưu lượng**; chỉ đo thời gian trả về của lời gọi `trace()` không đủ, vì công việc có thể được đẩy sang phía sau.

## 7. Dùng TRACE để điều tra một lỗi cụ thể

Giả sử người dùng báo giảm giá đôi lúc không áp dụng dù có mã khuyến mại. Nếu chỉ có:

~~~text
INFO requestId=r-52 operation=checkout outcome=success
~~~

ta không biết quy tắc nào đã loại mã. Có thể bật TRACE tạm thời ở thành phần tính giảm giá và ghi trạng thái kiểm tra được chọn lọc:

~~~text
TRACE requestId=r-52 step=load-promotion promotionCode=PUBLIC10 found=true
TRACE requestId=r-52 step=validate-promotion active=true
TRACE requestId=r-52 step=validate-minimum subtotalCents=95000 requiredCents=100000 matched=false
TRACE requestId=r-52 step=choose-discount applied=false reason=MINIMUM_NOT_MET
INFO  requestId=r-52 operation=checkout outcome=success
~~~

Những bản ghi trên là **minh họa**. Có đủ ngữ cảnh để kết luận quy tắc minimum không thỏa (`95.000 < 100.000` cent) mà không cần log dữ liệu thanh toán, địa chỉ, token hoặc thông tin cá nhân. Nếu mức INFO/WARN trước đó chưa thể hiện vấn đề, TRACE cho phép kiểm tra chuỗi quyết định.

Quy trình điều tra:

1. **Chốt triệu chứng và ID tương quan.** Lấy request ID, thời điểm, hành vi kỳ vọng và thực tế, phiên bản ứng dụng và đầu vào có thể tái hiện.
2. **Khoanh vùng logger cần bật.** Chọn class/package xử lý quy tắc nghi vấn; ghi lại mức hiện tại và thời hạn bật TRACE theo chính sách vận hành.
3. **Bật TRACE có kiểm soát.** Dùng cấu hình được ứng dụng hỗ trợ; nếu có thể, chỉ bật ở môi trường kiểm thử, một instance hoặc một tập request được chọn, không mở toàn hệ thống một cách vô thời hạn.
4. **Đối chiếu theo request ID và trình tự bước.** Kiểm tra nhánh điều kiện, dữ liệu được phép ghi và kết quả trung gian; xác định dòng dữ liệu trở nên sai. Đừng kết luận từ thứ tự log của nhiều thread khác nhau nếu không có quan hệ nhân quả rõ.
5. **Tái hiện, sửa nguyên nhân và viết test hồi quy.** Dùng debugger hoặc test để chứng minh điều kiện sai rồi xác nhận kết quả sau sửa. TRACE chỉ cung cấp dấu vết của những gì đã được ghi.
6. **Khôi phục mức log vận hành và quan sát.** Tắt TRACE khi hết phiên điều tra, kiểm tra volume đã giảm, giữ INFO/WARN/ERROR có ích và metric cần thiết.

Đối với bug đồng thời hoặc race condition, bật TRACE có thể làm thay đổi timing và khiến lỗi khó tái hiện. Kết hợp với test đồng thời, profiler, thread dump hoặc distributed tracing khi phù hợp; tránh xem một lần không thấy lỗi sau khi bật TRACE là bằng chứng đã sửa thành công.

## 8. Các nguyên tắc để TRACE dễ dùng

### Gắn ngữ cảnh ổn định

Ưu tiên `requestId`, `operation`, `component`, `step`, `outcome` và một vài giá trị kỹ thuật an toàn. Với luồng bất đồng bộ, đảm bảo context được truyền rõ ràng giữa các tác vụ. `MDC` trong các framework thường gắn với thread; không mặc định nó tự theo một request khi chuyển thread. Đừng dựa hoàn toàn vào timestamp để nối các sự kiện của nhiều request đang chạy đồng thời.

### Chọn cách ghi có cấu trúc

Sử dụng tên trường ổn định, đơn vị đo rõ ràng như `durationMs`, `sizeBytes`, `totalCents`, và giá trị status chuẩn hóa giúp tìm kiếm, so sánh và lọc. Nếu dùng JSON structured logging, bảo đảm formatter không xuất dữ liệu nhạy cảm. Không log object tràn lan chỉ vì muốn xem “mọi thứ”.

### Hạn chế khối lượng

Không thêm TRACE vào mọi dòng mà không có câu hỏi chẩn đoán. Vòng lặp nóng thường chỉ cần số lượng/nhánh tổng kết; thông tin từng phần tử có thể bật theo điều kiện, sampling hoặc bộ dữ liệu tái hiện. Sampling mất một phần dấu vết, vì vậy cần hiểu rằng nó có thể bỏ lỡ lỗi hiếm và không phù hợp với sự kiện bắt buộc lưu đầy đủ.

### Phối hợp các mức log

- **TRACE** trình bày đường đi chi tiết khi cần điều tra.
- **DEBUG** tóm tắt các quyết định kỹ thuật đủ để developer phân tích tình huống.
- **INFO** giữ mốc vận hành có ý nghĩa lâu dài.
- **WARN/ERROR** chỉ ra bất thường hoặc lỗi cần chú ý.

Việc lựa chọn mức là cân bằng giữa **khả năng chẩn đoán** và **khối lượng vận hành**. TRACE được dùng đúng sẽ rất hữu ích khi bật tạm thời, nhưng quá nhiều TRACE cố định làm nhiễu thông tin chính.

## 9. Hiểu nhầm và lỗi phổ biến

| Hiểu nhầm | Điều thực tế cần nhớ | Cách xử lý |
| --- | --- | --- |
| “TRACE là mức báo lỗi nghiêm trọng” | TRACE biểu thị chi tiết thực thi, không biểu thị severity cao | Ghi WARN/ERROR cho lỗi đúng mức |
| “TRACE và DEBUG giống hệt nhau” | TRACE thường chi tiết hơn, nhưng quy ước từng hệ thống khác nhau | Thống nhất quy ước theo thành phần |
| “Bật TRACE thì mọi dòng luôn xuất hiện” | Logger và backend/appender/filter có thể chặn | Kiểm tra cấu hình thực tế |
| “TRACE của JUL gọi là TRACE” | JUL dùng FINE/FINER/FINEST, không có mức tên TRACE | Phân biệt API và provider |
| “Dùng `{}` luôn trì hoãn mọi đối số” | Java vẫn đánh giá biểu thức đối số trước lời gọi | Dùng guard hoặc Supplier khi công việc đắt |
| “TRACE không có chi phí khi tắt” | Biểu thức eager vẫn chạy, kể cả khi log bị loại | Đo và dùng lazy message phù hợp |
| “TRACE giúp quan sát mọi biến trong chương trình” | Chỉ dữ liệu chủ động đưa vào message mới xuất hiện | Đặt câu hỏi cụ thể, bổ sung debugger/test |
| “Bật TRACE giúp có distributed trace” | TRACE level và trace/span là hai cơ chế khác nhau | Dùng tracing instrumentation nếu cần |
| “Log TRACE payload đầy đủ là an toàn” | Log có thể được lưu, sao chép, truy vấn rộng | Chỉ ghi trường an toàn, ẩn bí mật |
| “Async TRACE miễn phí và luôn không mất log” | Queue đầy/crash có thể gây block hoặc mất dữ liệu | Theo dõi queue/dropped events, thử sink lỗi |

## 10. Bài tập tự kiểm tra

1. Chạy **TraceLevelDemo.java** trên JDK 17. Giải thích vì sao `evenSum=6` không phụ thuộc việc TRACE có đang bật hay không. Liệt kê các message TRACE dự kiến khi provider cho phép mức này.
2. Trong một dự án SLF4J/Logback, đặt ngưỡng INFO cho toàn hệ thống rồi chỉ bật TRACE cho package đang lỗi. Kiểm tra rằng các logger bên ngoài package vẫn dùng ngưỡng kế thừa tương ứng; lưu ý các filter của appender.
3. Giải thích vì sao `LOG.trace("value={}", expensive())` có thể tốn CPU ngay cả khi TRACE bị tắt. Viết lại bằng `isTraceEnabled()` hoặc SLF4J 2 fluent API với Supplier.
4. Một dịch vụ tạo 4.000 request/giây và 5 dòng TRACE/request, trung bình 300 byte/dòng. Tính byte/giây và GB/ngày trước nén/index, rồi nêu hai cách giảm volume mà vẫn điều tra được một request cụ thể.
5. Đưa ra ba trường nên ghi khi TRACE kiểm tra logic discount, ba trường không được ghi nếu chứa dữ liệu nhạy cảm, và một tình huống TRACE có thể làm thay đổi hành vi chương trình.

**Ghi nhớ:** TRACE là mức log phục vụ phân tích **từng bước thực thi**. Dùng TRACE có chủ đích, gắn ID tương quan, bảo vệ dữ liệu, chọn cách dựng message tiết kiệm khi bị tắt và bật trong phạm vi/thời gian kiểm soát. Kết hợp với DEBUG, INFO, WARN/ERROR, debugger và tracing theo nhu cầu để có đủ thông tin tìm đúng nguyên nhân mà không làm quá tải hệ thống.