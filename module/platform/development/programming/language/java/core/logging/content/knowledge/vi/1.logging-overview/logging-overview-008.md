# Logging và debugging trong Java

## 1. Mục tiêu và sự khác biệt

Khi ứng dụng Java trả kết quả sai, chậm bất thường hoặc phát sinh exception, ta cần trả lời ba câu hỏi: **đã xảy ra chuyện gì**, **xảy ra ở ngữ cảnh nào**, và **vì sao mã chạy như vậy**. Logging và debugging hỗ trợ những câu hỏi này theo hai cách bổ sung nhau.

- **Logging (ghi nhật ký):** chương trình chủ động phát ra bản ghi về sự kiện khi chạy: thời điểm, mức độ nghiêm trọng, hành động, ngữ cảnh và kết quả. Bản ghi có thể được giữ lại để phân tích sau khi lỗi đã xảy ra, kể cả khi không thể tái hiện ngay.
- **Debugging (gỡ lỗi):** quá trình quan sát và kiểm chứng hành vi chương trình để tìm nguyên nhân lỗi. Debugger là công cụ cho phép đặt điểm dừng (breakpoint), xem biến, đi từng bước, xem call stack và luồng thực thi. Gỡ lỗi còn bao gồm tái hiện lỗi, đặt giả thuyết, thử nghiệm và kiểm chứng bản sửa.

| Tiêu chí | Logging | Debugging với debugger |
| --- | --- | --- |
| Thời điểm hữu ích | Khi ứng dụng đang chạy, đặc biệt tại môi trường tích hợp hoặc production | Khi tái hiện được vấn đề trong môi trường cho phép dừng/quan sát chương trình |
| Quan sát được | Những sự kiện và dữ liệu mà lập trình viên đã quyết định ghi | Trạng thái biến, biểu thức, stack frame, thread tại các điểm dừng |
| Tác động | Có chi phí CPU/I/O/lưu trữ; thường không cần dừng chương trình | Điểm dừng có thể làm thay đổi thời gian thực thi và tương tác giữa các thread |
| Giá trị chính | Dựng lại diễn biến, so sánh nhiều request/lần chạy, điều tra sự cố đã qua | Truy tìm nhánh điều kiện, dữ liệu trung gian và nguyên nhân tại dòng lệnh |
| Giới hạn | Không thể nhìn thấy dữ liệu chưa từng được ghi; log thiếu ngữ cảnh dễ gây hiểu nhầm | Khó bắt lỗi hiếm, lỗi timing hoặc sự cố chỉ xuất hiện trong production |

Ví dụ: nếu một API thỉnh thoảng trả tổng tiền sai, log có thể cho biết request nào, đầu vào nào và kết quả nào bất thường. Sau đó, dùng breakpoint với bộ dữ liệu tương ứng để xem phép tính hoặc nhánh điều kiện gây ra lỗi.

## 2. Logging: ghi đúng thông tin, đúng mức

### 2.1. Dùng logging API thay cho in tùy tiện

`System.out.println(...)` hữu ích cho bài tập nhỏ, nhưng thiếu mức độ log, cấu hình lọc, nguồn ghi và chính sách vận hành. Java có API chuẩn `java.util.logging` (JUL); Java 9+ còn có `System.Logger`. Trong ứng dụng dùng thư viện, ta thường thấy **SLF4J** làm API trung gian và **Logback/Log4j 2/JUL** làm cơ chế ghi. Đây là các lựa chọn trong hệ sinh thái, không phải các thư viện đều có sẵn trong JDK. Ví dụ bên dưới chỉ dùng JUL của JDK 17.

Logger thường được tạo theo tên lớp: `Logger.getLogger(TenLop.class.getName())`. Ghi sự kiện có ý nghĩa thay cho in mọi giá trị trung gian. Mỗi bản ghi nên giúp trả lời **sự kiện gì, ở đâu, với đối tượng/request nào, và kết quả ra sao**.

### 2.2. Chọn mức độ

Với JUL, các mức hay gặp (từ nghiêm trọng tới chi tiết hơn) là:

| Mức JUL | Dùng khi | Ví dụ |
| --- | --- | --- |
| `SEVERE` | Lỗi nghiêm trọng cần quan tâm, thao tác không hoàn thành | Không thể kết nối phụ thuộc bắt buộc, xử lý request thất bại |
| `WARNING` | Bất thường nhưng chương trình có thể tiếp tục hoặc đã có phương án dự phòng | Đầu vào không hợp lệ, lần thử lại sau thất bại |
| `INFO` | Mốc vận hành đáng biết | Khởi động thành công, tác vụ hoàn tất, thay đổi trạng thái quan trọng |
| `CONFIG` | Thông tin cấu hình phục vụ chẩn đoán | Chế độ hoặc tùy chọn cấu hình đã chọn, không gồm secret |
| `FINE` / `FINER` / `FINEST` | Diễn biến kỹ thuật cần khi phân tích sâu | Nhánh xử lý, giá trị trung gian, quyết định retry |

`Level.OFF` tắt ghi; `Level.ALL` cho phép mọi mức. Mức ở **logger** và ở **handler** đều ảnh hưởng việc bản ghi có được xuất ra hay không. Chẳng hạn, đặt logger ở `FINE` nhưng ConsoleHandler chỉ nhận từ `INFO` thì không thấy bản ghi `FINE`. Tên mức và cơ chế lọc của SLF4J/Logback thường dùng `ERROR/WARN/INFO/DEBUG/TRACE`; không đồng nhất máy móc tên mức giữa các hệ.

**Nguyên tắc:** chọn mức theo khả năng hành động và nhu cầu vận hành. Không dùng `SEVERE` cho những tình huống bình thường có thể dự kiến; cũng không dùng `INFO` để in nội dung của mọi vòng lặp.

### 2.3. Đặt log tại ranh giới có ý nghĩa

Nên có log ở những mốc quan trọng: bắt đầu/kết thúc tác vụ, thao tác với hệ thống bên ngoài, quyết định fallback/retry, kiểm tra đầu vào thất bại và nơi xử lý exception. Các trường ngữ cảnh thường hữu ích gồm `requestId`, `operation`, `recordId`, `durationMs`, `outcome`. Nếu có nhiều request đồng thời, một ID tương quan giúp nối các bản ghi cùng luồng xử lý.

Ví dụ thông điệp:

~~~text
INFO operation=checkout requestId=req-42 outcome=success durationMs=35
WARNING operation=checkout requestId=req-43 outcome=rejected reason=invalid_quantity
~~~

Đây là **mẫu log minh họa**, không phải chuẩn định dạng bắt buộc của JUL. Ứng dụng thực tế có thể xuất log dạng JSON hoặc trường có cấu trúc để hệ thống tìm kiếm dễ truy vấn. Không phụ thuộc vào thứ tự dòng log từ các thread để kết luận quan hệ nhân quả.

## 3. Ví dụ chạy được bằng JDK 17+

Tạo tệp **LoggingDebuggingDemo.java** với nội dung sau. Ví dụ tính giá sau giảm giá bằng số nguyên để tập trung vào quan sát chương trình; đây **không phải mô hình tính tiền có yêu cầu làm tròn thực tế**. Handler tự định dạng và ghi ra stdout chỉ để kết quả thực hành ổn định; ứng dụng production thường cấu hình handler/appender bên ngoài mã.

~~~java
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class LoggingDebuggingDemo {
    private static final Logger LOG =
            Logger.getLogger(LoggingDebuggingDemo.class.getName());

    static {
        LOG.setUseParentHandlers(false); // Tránh in trùng qua root logger.
        LOG.setLevel(Level.FINE);

        Handler output = new StreamHandler(System.out, new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + ": "
                        + formatMessage(record) + System.lineSeparator();
            }
        }) {
            @Override
            public synchronized void publish(LogRecord record) {
                super.publish(record);
                flush(); // Hiện ngay log trong ví dụ.
            }
        };
        output.setLevel(Level.FINE);
        LOG.addHandler(output);
    }

    static int finalPrice(int originalPrice, int discountPercent) {
        LOG.fine(() -> "originalPrice=" + originalPrice
                + ", discountPercent=" + discountPercent);

        if (originalPrice < 0 || discountPercent < 0
                || discountPercent > 100) {
            LOG.warning("Invalid input");
            throw new IllegalArgumentException("Invalid input");
        }

        // Đổi sang long trước phép nhân để tránh tràn int.
        long discount = (long) originalPrice * discountPercent / 100;
        int result = originalPrice - (int) discount;
        LOG.info(() -> "finalPrice=" + result);
        return result;
    }

    public static void main(String[] args) {
        System.out.println("Result=" + finalPrice(200, 10));
    }
}
~~~

Biên dịch và chạy tại thư mục chứa tệp:

~~~bash
javac -encoding UTF-8 -g LoggingDebuggingDemo.java
java LoggingDebuggingDemo
~~~

Đầu ra **stdout** của ví dụ trên:

~~~text
FINE: originalPrice=200, discountPercent=10
INFO: finalPrice=180
Result=180
~~~

Giải thích: `200 × 10 / 100 = 20` nên kết quả là `180`. Vì logger và handler đều cho phép `FINE`, cả dòng chi tiết và dòng `INFO` đều hiển thị. `-g` yêu cầu `javac` sinh thông tin debug (chẳng hạn thông tin dòng và biến cục bộ) để debugger dễ quan sát; nó không làm thay đổi công thức tính.

Trong chương trình bình thường, JUL thường có handler mặc định với cấu hình và định dạng khác; **không mặc định mong đợi đúng ba dòng trên** khi bỏ cấu hình riêng của ví dụ.

## 4. Debugging: tìm nguyên nhân ở cấp câu lệnh

### 4.1. Các thao tác cần biết

- **Breakpoint:** dừng trước một dòng hoặc trong phương thức nghi vấn. Breakpoint có điều kiện rất hữu ích khi lỗi chỉ xảy ra với `requestId` hay giá trị nhất định.
- **Step Over:** thực hiện dòng hiện tại rồi dừng ở dòng tiếp theo trong cùng frame; không đi sâu vào lời gọi phương thức.
- **Step Into:** đi vào phương thức được gọi để kiểm tra cách nó xử lý dữ liệu.
- **Step Out:** chạy nốt phương thức hiện tại và trở lại nơi gọi.
- **Variables / Evaluate / Watch:** xem biến, tính biểu thức, theo dõi giá trị thay đổi; cẩn thận khi evaluate biểu thức có tác dụng phụ.
- **Call Stack:** biết chuỗi phương thức dẫn tới điểm dừng; xem đúng frame để hiểu biến cục bộ và tham số.
- **Exception Breakpoint:** dừng tại nơi exception được ném (hoặc chưa được bắt, tùy cấu hình IDE), giúp tìm nguồn thay vì chỉ nhìn nơi in stack trace.
- **Threads:** khi xử lý đồng thời, xem thread nào đang dừng/đợi khóa. Dừng một thread có thể thay đổi hiện tượng race hoặc timeout.

Không cần đặt breakpoint ở mọi dòng. Hãy chọn một giả thuyết có thể kiểm chứng: **giá trị trở nên sai ở bước nào?** Bắt đầu ở gần đầu vào hoặc ranh giới phát hiện lỗi, rồi khoanh vùng dần.

### 4.2. Thực hành bằng IDE hoặc jdb

Trong IntelliJ IDEA, Eclipse hoặc VS Code có Java Debugger, đặt breakpoint tại dòng tính `discount`, chạy chế độ Debug, xem `originalPrice`, `discountPercent`, `discount` và `result`, sau đó Step Over qua từng phép gán.

JDK cũng đi kèm **jdb**, có thể thực hành trong terminal. Sau lệnh biên dịch có `-g` như mục 3:

~~~bash
jdb LoggingDebuggingDemo
~~~

Trong phiên jdb, lần lượt nhập:

~~~text
stop in LoggingDebuggingDemo.finalPrice
run
locals
next
locals
cont
quit
~~~

`stop in` đặt điểm dừng đầu phương thức; `run` bắt đầu chạy chương trình; `locals` xem biến cục bộ đang khả dụng; `next` thực thi bước kế tiếp; `cont` tiếp tục. Tùy dòng đang dừng, `locals` chỉ hiển thị các biến đã được khởi tạo. Đầu ra của jdb còn có prompt/thông báo phiên nên không có một transcript cố định giống stdout của chương trình.

### 4.3. Ví dụ sai do phép chia nguyên

Giả sử một hệ thống theo dõi tiến độ dùng:

~~~java
int processed = 3;
int total = 10;
double ratio = processed / total; // Sai mục đích: ratio nhận 0.0
~~~

Log `processed=3, total=10, ratio=0.0` chỉ ra triệu chứng. Breakpoint tại phép gán cho thấy **hai toán hạng đều là int**, nên Java thực hiện chia nguyên `3 / 10 = 0` rồi mới chuyển thành `double`. Sửa như sau:

~~~java
if (total <= 0) {
    throw new IllegalArgumentException("total must be positive");
}
double ratio = (double) processed / total; // 0.3
~~~

Sau sửa, chạy lại đúng bộ đầu vào và kiểm thử các ranh giới như `processed=0`, `processed=total`, `total=0`. Đây là ví dụ cho thấy log giúp xác định tình huống, còn debugger giải thích cơ chế ở dòng mã.

## 5. Quy trình kết hợp logging và debugging

1. **Mô tả lỗi có thể kiểm chứng.** Ghi rõ kết quả kỳ vọng, kết quả thực tế, phiên bản ứng dụng/JDK, đầu vào, môi trường và thời điểm; tìm cách tái hiện tối thiểu.
2. **Dựng lại diễn biến bằng log.** Lọc theo thời gian, request/correlation ID và tác vụ. Tìm sự kiện trước/sau lỗi, lời gọi ra ngoài, cảnh báo, stack trace. Kiểm tra log có bị thiếu bởi bộ lọc mức hoặc sampling không.
3. **Đặt giả thuyết cụ thể.** Ví dụ: “giá trị bị chia nguyên”, “nhánh retry chạy hai lần”, hoặc “dữ liệu bị thread khác cập nhật”. Tránh kết luận chỉ dựa trên một dòng log.
4. **Đặt điểm dừng ở chỗ có thể phân biệt giả thuyết.** Quan sát đầu vào, điều kiện nhánh, kết quả trung gian và call stack; dùng conditional breakpoint nếu nhiều lần lặp.
5. **Sửa nguyên nhân và kiểm thử hồi quy.** Tạo test đúng dữ liệu đã gây lỗi, thêm trường hợp biên; xác nhận cả hành vi đầu ra lẫn sự kiện log có ích. Bỏ log thăm dò ồn ào hoặc hạ mức phù hợp.
6. **Đối chiếu sau triển khai.** Sử dụng log/metrics để kiểm tra triệu chứng đã hết trong điều kiện thực tế; không coi một lần debug thành công là đủ chứng minh mọi tình huống đều đúng.

Khi lỗi chỉ xảy ra dưới tải, trong môi trường production hoặc do timing, ưu tiên log có ngữ cảnh, tracing/metrics và dữ liệu tái hiện. Breakpoint có thể làm lỗi race biến mất hoặc khiến request timeout; kết luận cần dựa thêm vào kiểm thử tải/đồng thời.

## 6. Exception, hiệu năng và an toàn thông tin

**Ghi exception có ngữ cảnh và stack trace:** nếu đây là nơi chịu trách nhiệm xử lý hoặc báo cáo lỗi, JUL có thể ghi đối tượng `Throwable`:

~~~java
// Đoạn minh họa bên trong một catch, không phải chương trình độc lập.
catch (java.io.IOException e) {
    LOG.log(Level.SEVERE, "operation=loadConfig outcome=failed", e);
    throw e;
}
~~~

Phương thức `log(Level, String, Throwable)` giữ lại stack trace. Tránh chỉ ghi `e.getMessage()` khi cần xác định nguồn lỗi. Đồng thời tránh ghi cùng một exception ở mọi tầng rồi tạo hàng loạt log `SEVERE` trùng nhau: chọn ranh giới phù hợp để báo cáo, còn các tầng khác có thể truyền lỗi lên.

**Chi phí ghi log:** thông điệp tạo chuỗi, serialize đối tượng hoặc lấy stack trace có thể tốn CPU, bộ nhớ và I/O. Với dữ liệu đắt để tính, `LOG.fine(() -> expensiveDescription())` dùng `Supplier` để chỉ tạo thông điệp khi mức đó được bật. Tuy vậy, không đặt logic có tác dụng phụ vào hàm dựng log; không ghi từng phần tử của một luồng dữ liệu lớn ở `INFO`. Tại production, cấu hình lọc, sampling, xoay vòng tệp, retention và quyền truy cập theo nhu cầu vận hành.

**Dữ liệu nhạy cảm:** không ghi password, token, API key, session cookie, dữ liệu cá nhân đầy đủ hoặc payload thô chứa bí mật. Hãy chọn trường an toàn, che/mã hóa phù hợp, giới hạn quyền truy cập và thời gian lưu. Log thường đi qua nhiều hệ thống; dữ liệu đã ghi có thể khó thu hồi.

**Thông tin có cấu trúc:** cố gắng giữ tên trường và kiểu biểu diễn nhất quán. Ghi cả `durationMs` và `outcome` giúp điều tra tốt hơn một thông điệp mơ hồ “done”. Đưa ID tương quan qua những tác vụ bất đồng bộ nếu muốn nối log của nhiều thread; context gắn với thread không tự động đi theo mọi tác vụ.

**Phân biệt môi trường:** cấu hình log level bằng cấu hình triển khai nếu có thể. Bật log chi tiết trong thời gian điều tra có kiểm soát rồi trả về mức vận hành thích hợp; không để cấu hình tutorial ghi stdout hoặc ghi mọi request chi tiết thành quy ước mặc định cho hệ thống lớn.

## 7. Các lỗi phổ biến và cách nhận biết

| Sai lầm | Hệ quả | Cách làm |
| --- | --- | --- |
| Chỉ dùng `System.out.println` cho vận hành | Khó lọc mức, phân loại và giữ ngữ cảnh | Dùng logging API cùng cấu hình nhất quán |
| Mong thấy `FINE` khi handler chỉ cho `INFO` | Tưởng chương trình không chạy đến đoạn mã | Kiểm tra cả mức logger và handler |
| Ghi “Error occurred” mà không có dữ liệu | Không tìm được request hay nguyên nhân | Ghi tên thao tác, ID tương quan, kết quả và exception khi phù hợp |
| Ghi exception ở nhiều tầng | Nhiễu, đếm sai số lần lỗi | Chọn ranh giới chịu trách nhiệm ghi lỗi |
| Ghi secret hoặc toàn bộ object | Rò rỉ dữ liệu, log phình to | Whitelist trường an toàn, ẩn dữ liệu nhạy cảm |
| Bật breakpoint trong lỗi race rồi không còn lỗi | Thời gian thực thi bị thay đổi | Bổ sung log/tracing, stress test và quan sát thread |
| Sửa khi chưa tái hiện hoặc chưa có test | Không biết đã sửa đúng nguyên nhân chưa | Tạo ca tái hiện và test hồi quy |
| Xem log là bằng chứng đầy đủ | Bỏ sót trạng thái chưa được ghi | Dùng debugger, test và metrics để xác nhận |

## 8. Bài tập tự kiểm tra

1. Chạy chương trình ở mục 3 và giải thích vì sao cả `FINE` lẫn `INFO` xuất hiện. Sau đó đổi **chỉ** `output.setLevel(Level.FINE)` thành `Level.INFO`: dự đoán dòng nào biến mất, đối chiếu kết quả chạy.
2. Đặt breakpoint tại phép tính `discount` và quan sát kiểu `long` của biểu thức nhân. Thử `finalPrice(100, 25)`; dự đoán `75` trước khi chạy.
3. Thử đầu vào `finalPrice(100, 120)` trong một lần gọi riêng, xem `WARNING` và exception; giải thích vì sao không có log `finalPrice=...` ở nhánh đó.
4. Với lỗi chia nguyên ở mục 4.3, viết một test kiểm tra `3/10` phải ra `0.3` (có sai số số thực thích hợp), rồi sửa toán hạng và chạy lại.

**Ghi nhớ khi thực hành:** log cung cấp lịch sử có thể truy tìm; debugger cho thấy trạng thái tại điểm dừng; kiểm thử xác nhận bản sửa. Kết hợp cả ba giúp đi từ triệu chứng tới nguyên nhân và ngăn lỗi tái diễn.