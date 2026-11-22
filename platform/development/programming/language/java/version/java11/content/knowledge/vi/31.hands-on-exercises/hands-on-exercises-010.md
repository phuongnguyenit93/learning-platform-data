# Ghi sự kiện nghiệp vụ và phân tích bản ghi JFR (Java 11+)

## 1. Mục tiêu và tình huống thực hành

Một dịch vụ xử lý đơn hàng cần trả lời: trong một khoảng thời gian có bao nhiêu yêu cầu thành công/thất bại, từng thao tác mất bao lâu, và lúc xảy ra độ trễ cao JVM đang làm gì? Ta sẽ tạo **sự kiện JFR do ứng dụng định nghĩa**, lưu thành tệp `.jfr`, đọc tệp để tổng hợp kết quả và biết cách điều tra một JVM đang chạy.

Hoàn thành bài này, bạn có thể:
- Thiết kế event nghiệp vụ có tên, nhóm, nhãn và dữ liệu có ý nghĩa.
- Phát event cho cả nhánh thành công và lỗi, đo đúng khoảng xử lý.
- Ghi và đọc recording bằng API `jdk.jfr` / `jdk.jfr.consumer`, có sẵn từ JDK 11.
- Dùng `jfr`, `jcmd` và JDK Mission Control (JMC) để kiểm tra và phân tích recording.
- Nhận biết giới hạn hiệu năng, bảo mật và độ tin cậy của JFR.

**Điều kiện:** JDK 11 trở lên (ví dụ dùng Java 17/21/25); kiểm tra `java -version`, `javac -version`, `jfr --help`. Dùng JDK đầy đủ để có công cụ dòng lệnh. Ví dụ chỉ dùng API có từ JDK 11, không yêu cầu thư viện ngoài hoặc cơ chế cũ.

## 2. JFR lưu gì, và khi nào tạo business event?

**Java Flight Recorder (JFR)** là cơ chế ghi sự kiện và dữ liệu chẩn đoán tích hợp trong JVM. Recording có thể chứa event của JVM như GC, thread, CPU, allocation và event do ứng dụng tự phát. Mỗi event có **loại sự kiện**, **thời điểm**, có thể có **thời lượng**, **thread**, **stack trace** (nếu bật), và các trường tùy chỉnh. Tệp nhị phân `.jfr` dùng để phân tích tại thời điểm khác; nó không phải tệp log văn bản.

Ví dụ nghiệp vụ: sau khi xử lý một đơn hàng, phát `demo.business.OrderProcessed` với `orderId` (mã mẫu không nhạy cảm), `outcome` = `SUCCESS` hoặc `FAILED`, `amountCents` và thời lượng xử lý. Business event trả lời “thao tác nào xảy ra, kết quả ra sao”; event JVM giúp điều tra vì sao một giai đoạn có thể chậm.

**Phân biệt công cụ:** JFR dùng cho chẩn đoán hiệu năng và tương quan sự kiện theo thời gian. Log hỗ trợ tra cứu thông điệp, metrics giúp giám sát liên tục, distributed tracing nối các dịch vụ; các công cụ này bổ trợ nhau. Recording có thể bị tắt, lọc, giới hạn dung lượng hoặc chỉ thu trong một cửa sổ thời gian, nên **không được coi số event JFR là sổ cái giao dịch/audit log bảo đảm đầy đủ**.

Quy ước thiết kế event:
- Tên có namespace ổn định (`demo.business.OrderProcessed`); đừng đổi tên/field tùy tiện vì chương trình phân tích phụ thuộc schema này.
- Chỉ ghi dữ liệu cần chẩn đoán. Không đưa mật khẩu, token, nội dung khách hàng, thông tin thanh toán hoặc dữ liệu định danh thô vào recording.
- Java JFR event hỗ trợ field kiểu nguyên thủy, `String`, `Thread` và `Class`; không khai báo `List`, enum hoặc đối tượng nghiệp vụ tùy ý rồi kỳ vọng JFR tự serialize. Chuyển sang giá trị đơn giản, có giới hạn độ dài.
- Dùng `event.begin()` trước thao tác và `event.commit()` sau thao tác để thu duration; với sự kiện tức thời chỉ `commit()` là đủ. `@StackTrace(false)` thường phù hợp event nghiệp vụ tần suất cao; bật stack trace có chủ đích khi chẩn đoán.

## 3. Bài thực hành hoàn chỉnh: ghi, dump và đọc JFR

Tạo tệp **`BusinessJfrDemo.java`** với toàn bộ nội dung sau. Chương trình chạy được bằng JDK 11+, ghi ba thao tác giả lập, sau đó chỉ đọc event `demo.business.OrderProcessed` để đếm thành công/thất bại và cộng số tiền đơn thành công.

~~~java
import java.nio.file.Path;
import jdk.jfr.Category;
import jdk.jfr.Description;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.StackTrace;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public final class BusinessJfrDemo {
    @Name("demo.business.OrderProcessed")
    @Label("Order processed")
    @Category({"Business", "Orders"})
    @Description("Outcome and latency for an order operation")
    @StackTrace(false)
    static final class OrderProcessed extends Event {
        @Label("Order ID") String orderId;
        @Label("Outcome") String outcome;
        @Label("Amount in cents") long amountCents;
    }

    public static void main(String[] args) throws Exception {
        Path file = Path.of("orders.jfr");
        try (Recording recording = new Recording()) {
            recording.enable(OrderProcessed.class)
                     .withoutThreshold()
                     .withoutStackTrace();
            recording.start();
            process("ORD-001", 15_000, true);
            process("ORD-002", 9_000, false);
            process("ORD-003", 18_000, true);
            recording.stop();
            recording.dump(file);
        }

        int success = 0;
        int failure = 0;
        long successfulAmountCents = 0;
        try (RecordingFile input = new RecordingFile(file)) {
            while (input.hasMoreEvents()) {
                RecordedEvent event = input.readEvent();
                if (!"demo.business.OrderProcessed".equals(
                        event.getEventType().getName())) {
                    continue;
                }
                String outcome = event.getString("outcome");
                if ("SUCCESS".equals(outcome)) {
                    success++;
                    successfulAmountCents += event.getLong("amountCents");
                } else if ("FAILED".equals(outcome)) {
                    failure++;
                }
            }
        }
        System.out.printf(
            "Processed=%d, succeeded=%d, failed=%d, successfulAmountCents=%d%n",
            success + failure, success, failure, successfulAmountCents);
    }

    private static void process(String id, long cents, boolean succeeds)
            throws InterruptedException {
        OrderProcessed event = new OrderProcessed();
        event.orderId = id;
        event.amountCents = cents;
        event.outcome = "FAILED";
        event.begin();
        try {
            Thread.sleep(10);
            if (succeeds) {
                event.outcome = "SUCCESS";
            }
        } finally {
            event.commit();
        }
    }
}
~~~

Chạy tại thư mục chứa mã:

~~~bash
javac --release 11 BusinessJfrDemo.java
java BusinessJfrDemo
jfr summary orders.jfr
jfr print --events demo.business.OrderProcessed orders.jfr
~~~

**Dòng stdout do chương trình Java in ra (chính xác):**

~~~text
Processed=3, succeeded=2, failed=1, successfulAmountCents=33000
~~~

Sau chạy có tệp `orders.jfr` tại thư mục làm việc. Lệnh `jfr summary` hiển thị thống kê các loại sự kiện trong tệp; `jfr print --events demo.business.OrderProcessed orders.jfr` hiển thị chi tiết ba event nghiệp vụ. Phần timestamp, duration, kích thước tệp và các event JVM khác phụ thuộc môi trường nên không có một stdout cố định cho hai lệnh `jfr`.

**Giải thích từng điểm mấu chốt:**
1. `@Name` là định danh ổn định để lọc và xử lý máy; `@Label`, `@Description`, `@Category` giúp người đọc nhận biết event trong công cụ phân tích.
2. `recording.enable(OrderProcessed.class).withoutThreshold()` bật event này và không lọc theo thời lượng, nhờ đó cả ba thao tác đều được ghi. `withoutStackTrace()` tránh thu stack trace không cần thiết trong ví dụ.
3. `recording.start()` bắt đầu thu; `recording.stop()` dừng; `recording.dump(file)` xuất recording ra tệp. `try-with-resources` đóng tài nguyên kể cả khi có lỗi.
4. `event.begin()` lấy mốc bắt đầu, `event.commit()` kết thúc và cố gắng ghi event. `finally` đảm bảo thao tác thất bại/ngoại lệ cũng được commit. Đặt mặc định `FAILED` giúp thao tác bị ngắt không bị tính nhầm là thành công.
5. `RecordingFile` đọc **từng event** thay vì tải toàn bộ tệp vào bộ nhớ; kiểm tra `getEventType().getName()` rồi mới gọi `getString("outcome")` và `getLong("amountCents")`. Vì vậy các event JVM không làm sai số liệu.
6. Tổng tiền chỉ cộng hai đơn `SUCCESS`: `15_000 + 18_000 = 33_000` cents. Đây là phép tính minh họa cách phân tích, **không phải báo cáo tài chính đáng tin cậy** lấy từ JFR.

Trong ứng dụng thực, thay `Thread.sleep(10)` bằng nghiệp vụ thật và đặt thời điểm `SUCCESS` sau khi công việc thực sự hoàn thành theo ngữ nghĩa của hệ thống (ví dụ sau bước xác nhận transaction). Với xử lý bất đồng bộ, cần xác định lại ranh giới đo, vì thời lượng một method không nhất thiết bằng thời lượng nghiệp vụ end-to-end.

## 4. Cách đọc và phân tích recording

### 4.1 Đọc event có chọn lọc

Một `RecordedEvent` cung cấp:
- `getStartTime()`, `getEndTime()`: mốc thời gian; `getDuration()`: `Duration` của event được đo từ `begin` tới `end`/`commit`.
- `getEventType().getName()`: tên type đã khai báo.
- `getString("outcome")`, `getLong("amountCents")`: dữ liệu tùy chỉnh theo schema; `hasField("fieldName")` hữu ích khi cần xử lý tệp của nhiều phiên bản schema.
- `getThread()` và `getStackTrace()`: ngữ cảnh nếu recording có thu; stack trace có thể là `null` vì đã tắt.

Ví dụ đoạn xử lý thêm **đặt bên trong vòng lặp đọc `RecordedEvent`**, sau khi đã lọc đúng tên event:

~~~java
long elapsedMillis = event.getDuration().toMillis();
String outcome = event.getString("outcome");
String orderId = event.getString("orderId");
// Tích lũy elapsedMillis theo outcome/time window; chỉ dùng orderId phù hợp chính sách dữ liệu.
~~~

Đoạn trên là **mảnh code tích hợp**, không phải một chương trình chạy độc lập. Với bản ghi lớn, duyệt bằng `RecordingFile` và tổng hợp từng dòng; không mặc định gọi `RecordingFile.readAllEvents(path)` vì cách đó giữ toàn bộ event trong bộ nhớ.

### 4.2 Đọc số liệu đúng nghĩa

| Chỉ số muốn biết | Cách rút ra từ event | Giới hạn cần hiểu |
| --- | --- | --- |
| Lượng thao tác quan sát được | Đếm `demo.business.OrderProcessed` trong khoảng thời gian recording | Chỉ phản ánh event đã thu; không phải tổng đơn hàng tuyệt đối |
| Số lỗi, tỷ lệ lỗi quan sát được | Đếm `outcome = FAILED`; chia cho tổng event của cùng kỳ | Nếu đặt threshold/sampling, mẫu có thể lệch |
| Thời lượng trung bình, p95 | Lấy `getDuration()`, phân nhóm theo loại/kết quả, sắp xếp để tính percentile | Với mẫu nhỏ, p95 không đại diện cho tải thật; duration phụ thuộc ranh giới đo |
| Số tiền thành công trong mẫu | Cộng `amountCents` của `SUCCESS` | Chỉ minh họa; nguồn thống kê tài chính phải là hệ thống dữ liệu nghiệp vụ |
| Nguyên nhân chậm có thể có | So trục thời gian event nghiệp vụ với GC, CPU, lock, thread, allocation | Trùng thời điểm là dấu hiệu điều tra, không tự chứng minh quan hệ nhân quả |

Khi tính p95 từ `n` thời lượng đã sắp xếp tăng dần, một quy ước phổ biến là chọn phần tử thứ `ceil(0.95 × n)` (đếm từ 1); hãy ghi rõ quy ước percentile và độ phân giải thời gian để so sánh giữa các báo cáo. Đừng dùng tổng số event nếu recording có đoạn bị ngắt hoặc lọc.

### 4.3 Dùng công cụ để xem và đối chiếu

- `jfr summary orders.jfr`: xác nhận tệp hợp lệ, event có được thu và số lượng từng loại.
- `jfr print --events demo.business.OrderProcessed orders.jfr`: xem danh sách riêng event nghiệp vụ, trường và thời lượng; có thể dùng `--json` để xuất dữ liệu phục vụ công cụ phân tích khác.
- **JDK Mission Control (JMC)**: mở `orders.jfr`, tìm event theo tên trong Event Browser, xem histogram/time range/thread và so cùng cửa sổ thời gian với event JVM được bật. JMC là công cụ riêng, không mặc nhiên đi kèm JDK.
- Có thể ghi thêm event JVM hữu ích (GC, CPU, thread park, execution samples...) tùy mục tiêu và cấu hình, nhưng luôn xác minh chúng **thực sự có trong tệp** trước khi kết luận.

## 5. Ghi dữ liệu từ JVM đang chạy bằng `jcmd`

Không cần sửa mã để bắt đầu một recording JFR trên JVM hỗ trợ; lệnh `jcmd` điều khiển JVM đích bằng quyền tương ứng với tiến trình. Thay `12345` bằng PID thực được liệt kê bởi `jcmd`, rồi chạy theo trình tự:

~~~bash
jcmd
jcmd 12345 JFR.start name=Orders settings=default
jcmd 12345 JFR.check
jcmd 12345 JFR.dump name=Orders filename=orders-live.jfr
jcmd 12345 JFR.stop name=Orders
jfr summary orders-live.jfr
jfr print --events demo.business.OrderProcessed orders-live.jfr
~~~

`JFR.dump` chụp dữ liệu recording đang hoạt động ra tệp, không đồng nghĩa dừng recording; `JFR.stop` mới dừng. Đường dẫn tương đối trong `filename` được hiểu theo môi trường của JVM đích, nên hãy dùng đường dẫn tuyệt đối phù hợp hệ điều hành khi cần tìm tệp chắc chắn. Kiểm tra quyền đọc/ghi, dung lượng đĩa và chính sách lưu trữ trước khi ghi bản production.

`settings=default` ưu tiên overhead thấp cho quan sát thường ngày; `settings=profile` thường thu chi tiết hơn và cần đánh giá chi phí trên tải thật. Nếu muốn tự động kết thúc, có thể thêm `duration=60s` vào `JFR.start` và chỉ định tệp xuất theo cách phù hợp. Các tuỳ chọn cấu hình phụ thuộc JDK đang vận hành: dùng `jcmd 12345 help JFR.start` để kiểm tra tại chỗ.

## 6. Đưa instrumentation vào ứng dụng thực tế

Mẫu tích hợp với service nên tuân thủ ba quy tắc:

1. **Gắn event với ranh giới nghiệp vụ chính xác.** Ví dụ event `PaymentAuthorized` chỉ đánh dấu `SUCCESS` khi bộ phận xử lý đã xác nhận kết quả tương ứng, không phải ngay khi bắt đầu gửi request. Với transaction hoặc xử lý qua queue, phân biệt trạng thái “đã nhận”, “đã xử lý”, “đã commit”.
2. **Giữ đường lỗi.** Tạo event, gán trạng thái mặc định lỗi, `begin`, xử lý trong `try`, chuyển sang `SUCCESS` khi thành công, và `commit` trong `finally`. Nếu cần thêm mã lỗi, dùng mã đã chuẩn hóa; tránh ghi exception message chứa dữ liệu nhạy cảm.
3. **Giảm chi phí khi tải cao.** Không tạo chuỗi lớn hoặc gọi API tốn kém chỉ để điền field. `event.isEnabled()` cho biết event có được thu; `event.shouldCommit()` xét cả điều kiện threshold, phù hợp để tránh phần tính toán metadata đắt đỏ sau khi đo thời lượng. Tắt stack trace nếu không cần; chọn điểm phát event và điều kiện bật có chủ đích.

**Ngưỡng thời lượng (`threshold`):** Khi chỉ điều tra thao tác chậm, có thể cấu hình:

~~~java
recording.enable(OrderProcessed.class)
         .withThreshold(java.time.Duration.ofMillis(50));
~~~

Lệnh trên chỉ giữ event có duration đạt ngưỡng, do đó các thao tác nhanh không xuất hiện. **Không tính tỷ lệ lỗi/throughput toàn bộ hệ thống từ một recording đã lọc ngưỡng**. Đối với thống kê bao phủ cả kết quả thành công/thất bại trong ví dụ, dùng `withoutThreshold()`.

**Quản lý schema:** Giữ tên event ổn định, đặt tên field nhất quán và có đơn vị rõ ràng như `amountCents`. Khi đổi schema, phía đọc nên kiểm tra `hasField(...)` hoặc version để xử lý tệp cũ; đảm bảo thay đổi không làm lộ dữ liệu. Tránh trường có giá trị cực dài hoặc cardinality cao khi không giúp điều tra.

**An toàn vận hành:** JFR thường có overhead nhỏ nhưng không bằng 0; tăng số event, stack trace và detail sẽ tăng chi phí. Giới hạn thời gian/dung lượng, bảo vệ tệp như dữ liệu nội bộ, kiểm soát người có quyền ghi/đọc, và xóa theo chính sách. Khi cần biểu đồ cảnh báo vận hành lâu dài, xuất metrics từ nguồn tin cậy thay vì duy trì giả định JFR luôn thu đủ sự kiện.

## 7. Bài tập tự kiểm tra và tiêu chí đạt

1. **Chạy demo** và xác nhận stdout đúng: `Processed=3, succeeded=2, failed=1, successfulAmountCents=33000`. Tệp `orders.jfr` tồn tại.
2. **Kiểm tra recording** bằng `jfr summary` và `jfr print --events demo.business.OrderProcessed`. Tìm đủ ba business event; xem `outcome`, `amountCents` và duration (có thể khác nhau mỗi lần chạy).
3. **Thay đổi dữ liệu**: đổi tham số `succeeds` của đơn `ORD-003` từ `true` thành `false`, chạy lại. Kết quả mong đợi: `Processed=3, succeeded=1, failed=2, successfulAmountCents=15000`.
4. **Khảo sát ngưỡng**: thử `withThreshold(Duration.ofMillis(50))` trong demo có `Thread.sleep(10)`. Số event có thể là 0 nếu mọi thao tác dưới 50 ms; kiểm tra thực tế vì lịch scheduler có thể gây dao động. Giải thích vì sao không thể dùng mẫu này tính tỷ lệ lỗi.
5. **Thử phân tích sâu**: thu recording của một ứng dụng đang chạy bằng `jcmd`, mở trong JMC, lọc event nghiệp vụ theo thời gian rồi đối chiếu thread/CPU/GC nếu recording có các loại event tương ứng. Viết kết luận dựa trên dữ liệu quan sát, nêu rõ giả thuyết chưa được xác thực.

**Checklist trước khi coi bài thành công:** event đúng ranh giới nghiệp vụ; cả success/failure được ghi; mã Java biên dịch trên JDK 11; tệp có event name/field dự kiến; bộ đọc lọc đúng type; số đếm/tổng tiền đúng ví dụ; không chứa bí mật; hiểu rõ độ bao phủ của recording.

## 8. Tài liệu chính thức còn áp dụng

- [JDK 11 — `jdk.jfr.Event` API](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Event.html)
- [JDK 11 — `Recording` API](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Recording.html)
- [JDK 11 — `RecordingFile` API](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html)
- [Dev.java — Configuring JFR](https://dev.java/learn/jvm/monitoring-troubleshooting/jfr/configure/)
- [Oracle — `jfr` command reference](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html)
- [Oracle — JDK Mission Control User Guide](https://docs.oracle.com/en/java/java-components/jdk-mission-control/9/user-guide/jdk-mission-control.html)

Các phần học ở trên dựa trên cơ chế `jdk.jfr` hiện hành và API có từ Java 11. Khi làm việc ở JDK mới hơn, tra tài liệu đúng phiên bản của JDK đang chạy để xác nhận tùy chọn CLI và chi phí cấu hình.