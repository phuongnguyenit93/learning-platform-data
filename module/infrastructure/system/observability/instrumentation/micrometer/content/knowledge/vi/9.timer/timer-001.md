# Timer đo thời lượng thao tác cùng số lần và tổng thời gian

Trong ứng dụng Java, nhiều câu hỏi vận hành xoay quanh thời gian: một lần gọi dịch vụ mất bao lâu, thao tác đã chạy bao nhiêu lần, tổng thời gian xử lý là bao nhiêu và độ trễ điển hình đang thay đổi ra sao. Micrometer cung cấp Timer để ghi nhận thời lượng của một thao tác cùng số lần thao tác được thực hiện.

Timer không chỉ là đồng hồ bấm giờ. Nó là meter có thể tổng hợp số lần ghi nhận, tổng thời gian và các thống kê phân phối tùy cấu hình. Nhờ vậy, ứng dụng có thể dùng cùng một điểm instrumentation để quan sát throughput, tổng thời gian tiêu tốn và độ trễ. Bài học này giới thiệu cách tạo timer, ghi nhận thời lượng bằng API Micrometer, đọc các thống kê cơ bản và lựa chọn cấu hình phân phối phù hợp.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích Timer ghi nhận cả thời lượng và số lần thao tác.
- Tạo timer với tên và tag phù hợp.
- Đo một đoạn mã bằng record(Runnable), recordCallable hoặc ghi một thời lượng đã biết.
- Đọc count, totalTime, mean và max theo đơn vị mong muốn.
- Dùng Timer.Sample khi cần chọn tag sau khi thao tác kết thúc.
- Phân biệt thống kê percentile phía client với histogram có thể tổng hợp ở backend.

## Timer đo những gì?

Timer được thiết kế cho những thao tác có thời lượng. Mỗi lần ghi nhận đóng góp vào hai số đo nền tảng:

- **Count:** số lần thao tác được ghi nhận.
- **Total time:** tổng thời lượng của tất cả lần ghi nhận.

Từ hai số đo này, có thể tính thời lượng trung bình:

\[\text{mean} = \frac{\text{total time}}{\text{count}}\]

Nếu chưa có lần ghi nhận nào, mean được xem là 0. Timer còn có thể cung cấp giá trị lớn nhất và thống kê phân phối khi registry cùng cấu hình hỗ trợ.

Ví dụ, một timer ghi nhận ba lần gọi dịch vụ với thời lượng 40 ms, 60 ms và 100 ms:

| Thống kê | Giá trị |
|---|---:|
| Count | 3 |
| Total time | 200 ms |
| Mean | 66,67 ms |
| Max | 100 ms |

Count cho biết số lần thao tác được ghi nhận, kể cả lần chạy kết thúc bằng exception nếu được bọc bằng API record; total time cho biết tổng thời gian cộng dồn. Đây là hai đại lượng khác nhau. Một thao tác có thể có count cao nhưng mỗi lần chạy rất nhanh, hoặc count thấp nhưng tổng thời gian lớn vì mỗi lần chạy kéo dài.

Timer cũng hữu ích để tính tốc độ xử lý. Nếu backend quan sát count tăng thêm 600 lần trong một phút, tốc độ trung bình trong khoảng đó là 10 lần/giây. Tốc độ thường được tính ở backend bằng phép toán trên counter tăng dần, ví dụ PromQL rate(metric_count[5m]).

## Khi nào dùng Timer?

Dùng Timer khi muốn đo thời gian của một thao tác có điểm bắt đầu và kết thúc rõ ràng:

- Thời gian xử lý HTTP request hoặc một route.
- Thời gian truy vấn cơ sở dữ liệu.
- Thời gian gọi payment gateway hoặc dịch vụ bên ngoài.
- Thời gian xử lý một message hoặc một batch.
- Thời gian thực hiện một bước trong quy trình nghiệp vụ.

Nếu chỉ cần đếm số lần sự kiện xảy ra mà không quan tâm thời lượng, dùng Counter. Nếu cần đo kích thước payload hoặc một giá trị số không phải thời gian, dùng DistributionSummary. Nếu cần quan sát một tác vụ dài đang chạy và thời gian đã trôi qua trước khi nó hoàn thành, cân nhắc LongTaskTimer.

Không cần tạo thêm một counter riêng chỉ để đếm số lần của cùng thao tác đã được đo bằng timer. Timer.count() đã cung cấp số lần ghi nhận đó.

## Tạo và đăng ký Timer

Timer được đăng ký qua MeterRegistry. Có thể dùng API ngắn gọn:

~~~java
Timer timer = registry.timer(
    "checkout.processing",
    "operation", "authorize"
);
~~~

Hoặc dùng builder để khai báo mô tả, tag và cấu hình phân phối:

~~~java
Timer timer = Timer.builder("checkout.processing")
    .description("Thời gian xử lý bước checkout")
    .tag("operation", "authorize")
    .register(registry);
~~~

Tên meter nên mô tả đại lượng được đo, còn tag thể hiện những chiều phân tích có giá trị. Ví dụ, operation=authorize có thể phân biệt bước xác thực thanh toán với operation=capture. Tag phải có miền giá trị nhỏ và ổn định; không đưa request ID, user ID hoặc URL chứa ID động vào timer.

Khi cùng tên và cùng tập tag được đăng ký nhiều lần trên cùng registry, Micrometer tìm và tái sử dụng meter tương ứng. Nếu tag khác nhau, một meter ID khác được tạo. Vì thế, cần thiết kế tag trước khi đưa instrumentation vào luồng xử lý có lưu lượng lớn.

## Ghi nhận thời lượng bằng Timer

### Dùng record(Runnable)

Đây là cách trực tiếp khi đoạn mã cần đo không trả về kết quả:

~~~java
Timer timer = registry.timer("inventory.lookup");

timer.record(() -> {
    inventoryService.findAvailableItems();
});
~~~

Micrometer bắt đầu đo trước khi chạy đoạn mã và kết thúc phép đo khi đoạn mã hoàn tất. Thời lượng được ghi nhận ngay cả khi đoạn mã ném exception; exception vẫn được truyền ra cho mã gọi xử lý.

Cách này phù hợp khi muốn đo một khối công việc ngắn và không cần tự quản lý thời điểm bắt đầu/kết thúc.

### Dùng recordCallable khi cần kết quả trả về

Nếu thao tác trả về một giá trị, có thể dùng recordCallable:

~~~java
Timer timer = registry.timer("catalog.search");

SearchResult result = timer.recordCallable(
    () -> catalogService.search(query)
);
~~~

Giá trị trả về của callable được trả lại cho bên gọi. Nếu callable ném checked exception, phương thức gọi cần xử lý hoặc khai báo exception tương ứng. Timer vẫn ghi nhận thời lượng thực thi của callable.

### Ghi một thời lượng đã biết

Khi đã có thời lượng từ một nguồn khác hoặc đang viết ví dụ xác định, có thể gọi record(long, TimeUnit):

~~~java
timer.record(120, TimeUnit.MILLISECONDS);
timer.record(80, TimeUnit.MILLISECONDS);
~~~

Mỗi lời gọi đóng góp một lần vào count và thời lượng tương ứng vào total time. Cách này hữu ích trong kiểm thử, mô phỏng hoặc khi đo thời gian ở một lớp khác. Trong mã nghiệp vụ thông thường, nên để timer trực tiếp bao quanh thao tác cần đo để giảm nguy cơ tính sai thời lượng.

### Bọc Runnable để đo khi thực thi sau

wrap(Runnable) tạo một Runnable mới có hành vi ghi nhận thời lượng khi được chạy:

~~~java
Runnable timedTask = timer.wrap(() -> reportGenerator.generate());
executor.execute(timedTask);
~~~

Đoạn mã chỉ được ghi nhận khi timedTask thực sự được thực thi. Cách này hữu ích khi truyền công việc sang executor hoặc API chỉ nhận callback. Nếu task bị hủy trước khi chạy, không có thời lượng thực thi để ghi nhận.

## Ví dụ Java hoàn chỉnh

Ví dụ dưới đây dùng SimpleMeterRegistry để minh họa timer mà không cần Spring Boot hoặc backend giám sát:

~~~java
package example;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import java.util.concurrent.TimeUnit;

public class TimerDemo {

    public static void main(String[] args) {
        MeterRegistry registry = new SimpleMeterRegistry();

        try {
            Timer checkoutTimer = Timer.builder("checkout.processing")
                .description("Thời lượng xử lý checkout")
                .tag("operation", "authorize")
                .register(registry);

            // Ghi hai thời lượng xác định để minh họa count và total time.
            checkoutTimer.record(120, TimeUnit.MILLISECONDS);
            checkoutTimer.record(80, TimeUnit.MILLISECONDS);

            System.out.println("Count: " + checkoutTimer.count());
            System.out.println(
                "Total time (ms): "
                    + checkoutTimer.totalTime(TimeUnit.MILLISECONDS)
            );
            System.out.println(
                "Mean (ms): "
                    + checkoutTimer.mean(TimeUnit.MILLISECONDS)
            );
            System.out.println(
                "Max (ms): "
                    + checkoutTimer.max(TimeUnit.MILLISECONDS)
            );

            // Trong ứng dụng thật, đo trực tiếp đoạn công việc.
            checkoutTimer.record(() -> authorizePayment());
            System.out.println(
                "Count after payment: " + checkoutTimer.count()
            );
        } finally {
            registry.close();
        }
    }

    private static void authorizePayment() {
        // Thay bằng lời gọi gateway hoặc thao tác cần đo.
    }
}
~~~

Sau hai lần ghi nhận đầu tiên, các giá trị dự kiến là:

- Count bằng 2.
- Total time bằng 200 ms.
- Mean bằng 100 ms.
- Max bằng 120 ms.

Sau khi gọi authorizePayment(), count tăng thêm một. Thời lượng lần gọi này phụ thuộc công việc thực tế; nếu phương thức rỗng như trong ví dụ, thời gian rất nhỏ và không nên dùng để suy luận hiệu năng của một gateway thật.

SimpleMeterRegistry giữ số đo trong bộ nhớ. Nó phù hợp cho học tập và kiểm thử logic ghi nhận; nó không tự mở endpoint Prometheus hoặc gửi dữ liệu đến hệ thống giám sát.

## Đọc các thống kê của Timer

Timer cung cấp một số phương thức đọc phổ biến:

| API | Ý nghĩa |
|---|---|
| count() | Tổng số lần ghi nhận |
| totalTime(unit) | Tổng thời gian theo đơn vị yêu cầu |
| mean(unit) | Thời lượng trung bình theo đơn vị yêu cầu |
| max(unit) | Thời lượng lớn nhất trong cửa sổ thống kê hiện tại |
| measure() | Các measurement mà timer công bố |

### Count

count() trả về số lần timer đã ghi nhận. Với timer HTTP, đây có thể là số request được đo. Với timer truy vấn database, đây là số lần thực hiện truy vấn đã được ghi nhận.

Count không phải số request đang chạy. Timer thường ghi nhận khi thao tác hoàn thành; nếu cần theo dõi số tác vụ còn đang hoạt động, dùng gauge hoặc LongTaskTimer tùy ý nghĩa.

### Total time

totalTime(TimeUnit) trả về tổng thời gian đã ghi nhận, được chuyển sang đơn vị chỉ định. Ví dụ:

~~~java
double totalMillis = timer.totalTime(TimeUnit.MILLISECONDS);
double totalSeconds = timer.totalTime(TimeUnit.SECONDS);
~~~

Nên chọn đơn vị phù hợp với câu hỏi cần trả lời. Micrometer quản lý đơn vị thời gian bên trong và chuyển đổi khi đọc hoặc export theo registry. Đừng giả định mọi backend đều biểu diễn thời gian bằng cùng một đơn vị.

### Mean

mean(TimeUnit) trả về thời lượng trung bình của các lần ghi nhận. Với count lớn hơn 0, giá trị này tương ứng tổng thời gian chia cho số lần ghi nhận. Mean hữu ích để theo dõi xu hướng chung, nhưng có thể che khuất một số ít request rất chậm. Vì vậy không nên chỉ dựa vào mean để đánh giá độ trễ.

### Max

max(TimeUnit) trả về thời lượng lớn nhất trong cửa sổ thống kê mà timer đang sử dụng. Với các implementation Micrometer phổ biến, max là thống kê phân phối có tính chất cửa sổ thời gian; khi không có quan sát mới trong thời gian đủ dài, giá trị max có thể trở về 0 sau khi cửa sổ hết hạn. Vì vậy max không nhất thiết là giá trị lớn nhất kể từ khi ứng dụng khởi động.

Nếu cần phân tích đuôi phân phối, chẳng hạn p95 hoặc p99, hãy cấu hình percentile hoặc histogram thay vì xem max là đại diện cho toàn bộ độ trễ.

## Dùng Timer.Sample khi cần quyết định tag sau khi thao tác kết thúc

Thông thường, tag được biết trước khi bắt đầu đo. Nhưng đôi khi cần chọn tag dựa trên kết quả của thao tác, ví dụ thanh toán thành công hay thất bại. Timer.Sample cho phép bắt đầu đo trước, rồi chọn timer đích khi dừng:

~~~java
Timer.Sample sample = Timer.start(registry);
String outcome = "success";

try {
    paymentGateway.charge(command);
} catch (RuntimeException exception) {
    outcome = "error";
    throw exception;
} finally {
    Timer timer = Timer.builder("payment.processing")
        .tag("provider", "gateway")
        .tag("outcome", outcome)
        .register(registry);

    sample.stop(timer);
}
~~~

Timer.start(registry) bắt đầu sample bằng clock của registry. Khi gọi sample.stop(timer), thời lượng được ghi vào timer đã chọn. Vì tag outcome chỉ được xác định sau khi thao tác kết thúc, đây là cách phù hợp để phân nhóm theo kết quả.

Hãy giữ tập giá trị outcome hữu hạn, chẳng hạn success, error hoặc rejected. Không gắn thông báo exception nguyên văn vào timer. Nếu cần điều tra chi tiết lỗi, hãy ghi log hoặc trace với dữ liệu đã được kiểm soát.

Không gọi sample.stop nhiều lần cho cùng một lần thực thi. Mỗi sample biểu diễn một khoảng đo; hãy dừng đúng một lần trong nhánh kết thúc thích hợp.

## Đo nhiều thao tác và chọn phạm vi đo đúng

Một timer nên bao quanh đúng thao tác mà tên và tag của nó mô tả. Ví dụ, payment.authorization nên đo bước authorization, không bao gồm thời gian người dùng nhập biểu mẫu hoặc thời gian xử lý một tác vụ không liên quan.

~~~java
Timer authorizationTimer = registry.timer(
    "payment.authorization",
    "provider", "gateway"
);

authorizationTimer.record(() -> paymentGateway.authorize(command));
~~~

Nếu muốn đo toàn bộ checkout, tạo timer khác bao quanh toàn bộ luồng checkout. Hai timer có thể lồng nhau nếu có mục đích rõ ràng, nhưng không nên cộng total time của chúng như thể đó là hai phần thời gian độc lập: cùng một khoảng thời gian có thể xuất hiện trong cả phép đo cha và phép đo con.

Với thao tác bất đồng bộ, hãy chọn điểm bắt đầu và kết thúc tương ứng với vòng đời thực của công việc. Không đo chỉ thời gian tạo Future rồi coi đó là thời gian hoàn tất tác vụ. Có thể dùng callback hoặc sample để dừng timer khi kết quả bất đồng bộ hoàn tất; phải xử lý cả nhánh thành công, thất bại và hủy theo đúng yêu cầu nghiệp vụ.

## Histogram và percentile

Count và total time cung cấp cái nhìn tổng hợp nhưng không mô tả đầy đủ phân phối. Hai hệ thống có thể có cùng mean nhưng độ trễ p95 rất khác nhau. Micrometer cho phép cấu hình thống kê phân phối trên builder:

~~~java
Timer requestTimer = Timer.builder("http.server.requests")
    .tag("route", "/orders/{id}")
    .publishPercentiles(0.5, 0.95, 0.99)
    .publishPercentileHistogram()
    .serviceLevelObjectives(
        Duration.ofMillis(100),
        Duration.ofMillis(300),
        Duration.ofSeconds(1)
    )
    .register(registry);
~~~

Ba cơ chế cần phân biệt:

- publishPercentiles(...) yêu cầu tính các percentile phía client. Các giá trị này hữu ích để xem phân phối tại từng process, nhưng không thể cộng hoặc lấy trung bình percentile từ nhiều instance để có percentile chính xác cho toàn cụm.
- publishPercentileHistogram() yêu cầu xuất histogram theo khả năng của registry. Với backend hỗ trợ bucket histogram, dữ liệu từ nhiều instance có thể được tổng hợp trước khi tính percentile.
- serviceLevelObjectives(...) khai báo các ngưỡng thời lượng quan tâm. Với registry hỗ trợ, các ngưỡng này có thể được xuất như bucket ranh giới để truy vấn tỷ lệ thao tác hoàn tất trong mục tiêu.

Histogram tạo thêm dữ liệu cho mỗi meter ID. Chỉ bật khi dashboard hoặc alert cần phân tích phân phối; chọn bucket/SLO phù hợp để tránh tăng cardinality và chi phí lưu trữ không cần thiết.

## Đọc Timer ở backend Prometheus

Khi dùng registry Prometheus, một timer thường được biểu diễn thành các chuỗi cho count và sum; tên metric và đơn vị cụ thể tuân theo quy tắc export của registry. Một ví dụ minh họa có thể có dạng:

~~~text
checkout_processing_seconds_count{operation="authorize"} 2
checkout_processing_seconds_sum{operation="authorize"} 0.2
~~~

Count là số lần ghi nhận; sum là tổng thời gian theo giây trong ví dụ. Từ hai chuỗi này, Prometheus có thể tính tốc độ request:

~~~promql
rate(checkout_processing_seconds_count[5m])
~~~

Và thời lượng trung bình trong cửa sổ năm phút:

~~~promql
rate(checkout_processing_seconds_sum[5m])
/
rate(checkout_processing_seconds_count[5m])
~~~

Khi timer xuất histogram bucket, có thể tính percentile trên nhiều instance. Ví dụ p95:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
~~~

Tên metric trong truy vấn là ví dụ; hãy kiểm tra endpoint export để dùng đúng tên và đơn vị do registry thực tế tạo ra. Khi cần nhóm theo route hoặc method, giữ các label đó trong phép tổng hợp; khi muốn percentile toàn ứng dụng, tổng hợp các bucket theo le trước khi gọi histogram_quantile.

Không lấy trung bình p95 của từng instance để tạo p95 toàn cụm. Hãy tổng hợp histogram bucket rồi mới tính percentile.

## Chọn tag cho Timer

Tag nên cho biết thao tác được đo trong bối cảnh nào mà không tạo cardinality cao:

| Tag phù hợp | Ví dụ giá trị |
|---|---|
| operation | authorize, capture, refund |
| provider | gateway_a, gateway_b |
| route | /orders, /orders/{id} |
| method | GET, POST |
| outcome | success, error, rejected |

Tránh các tag như user ID, request ID, order ID, URL thực tế có ID động hoặc exception message. Mỗi tổ hợp tag có thể tạo meter ID và time series riêng; histogram còn nhân số chuỗi thống kê cho mỗi meter ID.

Nếu cần liên kết một quan sát độ trễ với request cụ thể, dùng trace context hoặc correlation ID trong log. Metrics nên giữ các tag tổng hợp để có thể so sánh xu hướng và tạo cảnh báo.

## Timer và LongTaskTimer

Timer thường ghi nhận thời lượng sau khi thao tác hoàn tất. Khi cần theo dõi một công việc dài vẫn đang chạy, LongTaskTimer có ý nghĩa khác: nó cung cấp thông tin về số task đang hoạt động và thời gian đã trôi qua của những task đó trước khi chúng hoàn tất.

Ví dụ, timer thông thường phù hợp với thời gian xử lý một HTTP request đã hoàn thành. Long task timer phù hợp hơn để quan sát một tác vụ đồng bộ dài, như tạo báo cáo lớn hoặc chạy một quy trình bảo trì kéo dài, khi bạn muốn biết hiện có bao nhiêu task đang hoạt động và chúng đã chạy bao lâu.

Không thay timer bằng long task timer chỉ vì thao tác có thể chậm. Hãy chọn theo câu hỏi cần trả lời: thời lượng của các lần đã hoàn tất hay trạng thái của công việc đang chạy.

## Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Count bằng 0 | Chưa gọi record hoặc đang đọc meter khác tag | Kiểm tra lời gọi ghi nhận và meter ID |
| Total time bằng 0 | Thao tác chưa được đo hoặc đơn vị đọc không phù hợp | Kiểm tra vị trí record và TimeUnit |
| Mean thấp nhưng người dùng vẫn thấy request rất chậm | Một số ít request chậm bị che bởi mean | Xem p95/p99 hoặc histogram |
| Max trở về 0 sau một thời gian | Cửa sổ thống kê max đã hết hạn mà không có quan sát mới | Hiểu semantics cửa sổ max; dùng histogram/percentile cho phân phối |
| Count tăng gấp đôi | Cùng thao tác bị đo ở hai lớp hoặc hai instrumentation cùng chạy | Xác định ranh giới đo và bỏ phép ghi trùng |
| p95 từng instance khác p95 toàn cụm | Percentile phía client không thể gộp trực tiếp | Tổng hợp histogram bucket trước khi tính percentile |
| Có quá nhiều series | Tag có miền giá trị lớn hoặc histogram không cần thiết | Chuẩn hóa tag và cấu hình phân phối theo nhu cầu |

## Kiểm thử Timer

Có thể dùng SimpleMeterRegistry để kiểm thử số lần và tổng thời gian mà không cần kết nối backend:

~~~java
SimpleMeterRegistry registry = new SimpleMeterRegistry();

Timer timer = registry.timer(
    "checkout.processing",
    "operation", "authorize"
);

timer.record(120, TimeUnit.MILLISECONDS);
timer.record(80, TimeUnit.MILLISECONDS);

assertEquals(2, timer.count());
assertEquals(200.0, timer.totalTime(TimeUnit.MILLISECONDS));
assertEquals(100.0, timer.mean(TimeUnit.MILLISECONDS));

registry.close();
~~~

Kiểm thử này xác nhận hai lần ghi nhận được tính vào count và tổng thời gian. Có thể bổ sung kiểm thử cho record(Runnable) bằng một thao tác mô phỏng, nhưng không nên khẳng định một thời lượng chính xác khi thời gian chạy phụ thuộc scheduler và tải máy.

Đối với instrumentation trong ứng dụng, nên kiểm tra:

- Timer được đăng ký với đúng tên và tag.
- Mỗi lần thao tác hoàn tất chỉ ghi nhận một lần.
- Nhánh exception vẫn được đo nếu đó là hành vi mong muốn.
- Tag outcome được chọn đúng theo kết quả.
- Cấu hình histogram/SLO chỉ áp dụng cho những timer cần phân tích phân phối.
- Tổng thời gian và count được đọc với đơn vị phù hợp.

Kiểm thử với SimpleMeterRegistry xác nhận logic ở cấp ứng dụng. Cần kiểm thử tích hợp riêng nếu muốn xác nhận tên metric, đơn vị, bucket hoặc giao thức export của backend.

## Ghi nhớ

- Timer đo thời lượng thao tác và tự ghi nhận số lần thực hiện.
- count() là số lần ghi nhận; totalTime(unit) là tổng thời gian.
- mean(unit) là thời lượng trung bình; max(unit) phản ánh max trong cửa sổ thống kê hiện tại.
- Dùng record(Runnable) hoặc recordCallable để bao quanh thao tác; dùng record(amount, unit) khi đã có thời lượng.
- Dùng Timer.Sample khi cần chọn meter hoặc tag sau khi thao tác kết thúc.
- Percentile phía client không thể gộp trực tiếp giữa nhiều instance; histogram bucket phù hợp hơn cho tổng hợp phân tán.
- Giữ tag hữu hạn và ổn định; không dùng ID cá thể hoặc thông báo lỗi làm tag.
- Dùng LongTaskTimer khi cần quan sát các task vẫn đang chạy.
- SimpleMeterRegistry phù hợp cho học và kiểm thử; cần registry export khi muốn đưa metrics đến hệ thống giám sát.

Khi đặt timer đúng ranh giới thao tác và chọn thống kê phù hợp, bạn có thể trả lời đồng thời ba câu hỏi quan trọng: thao tác chạy bao nhiêu lần, tiêu tốn tổng cộng bao nhiêu thời gian và phân phối độ trễ có đáp ứng mục tiêu vận hành hay không.
